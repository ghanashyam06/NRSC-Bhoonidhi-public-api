"""
Comprehensive Test Suite for ISRO Bhoonidhi STAC Portal & GEE Verification Engine.

Covers:
  - Error Handling & Custom Exception Hierarchy
  - Authentication & Token Refresh Workflows
  - STAC Search Engine & Parameter Constraints
  - Batch Download & GeoTIFF Raster Discovery
  - Google Earth Engine (ee.Image) Verifier & Code Generators
  - Map AOI Geometry, Initial State & Feasibility Calculations
"""

from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
import zipfile
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import requests

import app
import bhoonidhi_client as client
from bhoonidhi_client import (
    BhoonidhiError,
    BhoonidhiAuthError,
    BhoonidhiTimeoutError,
    BhoonidhiRateLimitError,
    BhoonidhiDateRangeError,
    BhoonidhiGatewayError,
    BhoonidhiNetworkError,
    BhoonidhiDownloadError,
)
import gee_verifier as gee


class TestBhoonidhiExceptionsAndAuth(unittest.TestCase):
    """Test exception hierarchy and authentication flows."""

    def test_custom_exception_hierarchy(self):
        """Verify all custom exceptions inherit properly from BhoonidhiError."""
        self.assertTrue(issubclass(BhoonidhiAuthError, BhoonidhiError))
        self.assertTrue(issubclass(BhoonidhiTimeoutError, BhoonidhiError))
        self.assertTrue(issubclass(BhoonidhiRateLimitError, BhoonidhiError))
        self.assertTrue(issubclass(BhoonidhiDateRangeError, BhoonidhiError))
        self.assertTrue(issubclass(BhoonidhiGatewayError, BhoonidhiError))
        self.assertTrue(issubclass(BhoonidhiNetworkError, BhoonidhiError))
        self.assertTrue(issubclass(BhoonidhiDownloadError, BhoonidhiError))

    def test_missing_credentials_raises_auth_error(self):
        """Verify missing environment variables raise BhoonidhiAuthError."""
        with patch.dict("os.environ", {"BHOONIDHI_USER_ID": "", "BHOONIDHI_PASSWORD": ""}):
            with self.assertRaises(BhoonidhiAuthError) as ctx:
                client.authenticate()
            self.assertIn("must be configured", str(ctx.exception))

    @patch("bhoonidhi_client.requests.post")
    def test_auth_success(self, mock_post):
        """Verify successful authentication stores tokens and returns access token."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "access_token": "mock_access_token_12345",
            "token_type": "Bearer",
            "expires_in": 1200,
            "refresh_token": "mock_refresh_token_67890",
        }
        mock_resp.raise_for_status.return_value = None
        mock_post.return_value = mock_resp

        with patch.dict("os.environ", {"BHOONIDHI_USER_ID": "shyam06", "BHOONIDHI_PASSWORD": "pwd"}):
            token = client.authenticate()
            self.assertEqual(token, "mock_access_token_12345")
            self.assertEqual(client.get_valid_token(), "mock_access_token_12345")

    @patch("bhoonidhi_client.requests.post")
    def test_auth_bad_request_hyphen(self, mock_post):
        """Verify userId with hyphens generates helpful diagnostic message."""
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.text = '{"Action": "Invalid UserID format"}'
        mock_resp.json.return_value = {"Action": "Invalid UserID format"}
        mock_post.return_value = mock_resp

        with patch.dict("os.environ", {"BHOONIDHI_USER_ID": "user-test", "BHOONIDHI_PASSWORD": "pwd"}):
            with self.assertRaises(BhoonidhiAuthError) as ctx:
                client.authenticate()
            self.assertIn("does not accept hyphens", str(ctx.exception))

    @patch("bhoonidhi_client.requests.post")
    def test_auth_unauthorized_401(self, mock_post):
        """Verify 401 Unauthorized raises BhoonidhiAuthError."""
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.text = "Unauthorized"
        mock_post.return_value = mock_resp

        with patch.dict("os.environ", {"BHOONIDHI_USER_ID": "shyam06", "BHOONIDHI_PASSWORD": "wrong"}):
            with self.assertRaises(BhoonidhiAuthError) as ctx:
                client.authenticate()
            self.assertIn("401 Unauthorized", str(ctx.exception))

    @patch("bhoonidhi_client.requests.post")
    def test_auth_rate_limit_429(self, mock_post):
        """Verify 429 Too Many Requests raises BhoonidhiRateLimitError."""
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_resp.text = "Rate limited"
        mock_post.return_value = mock_resp

        with patch.dict("os.environ", {"BHOONIDHI_USER_ID": "shyam06", "BHOONIDHI_PASSWORD": "pwd"}):
            with self.assertRaises(BhoonidhiRateLimitError):
                client.authenticate()

    @patch("bhoonidhi_client.requests.post")
    def test_auth_timeout(self, mock_post):
        """Verify requests.Timeout raises BhoonidhiTimeoutError."""
        mock_post.side_effect = requests.Timeout("Gateway timed out")
        with patch.dict("os.environ", {"BHOONIDHI_USER_ID": "shyam06", "BHOONIDHI_PASSWORD": "pwd"}):
            with self.assertRaises(BhoonidhiTimeoutError):
                client.authenticate(timeout=2)

    @patch("bhoonidhi_client.requests.post")
    def test_auth_connection_error(self, mock_post):
        """Verify network connection failures raise BhoonidhiNetworkError."""
        mock_post.side_effect = requests.ConnectionError("Failed to resolve host")
        with patch.dict("os.environ", {"BHOONIDHI_USER_ID": "shyam06", "BHOONIDHI_PASSWORD": "pwd"}):
            with self.assertRaises(BhoonidhiNetworkError):
                client.authenticate(timeout=2)


class TestSTACSearchAndDownload(unittest.TestCase):
    """Test STAC catalog searching, pagination, size checking, and downloading."""

    @patch("bhoonidhi_client.requests.post")
    def test_search_stac_pagination(self, mock_post):
        """Verify STAC search follows pagination 'next' links and gathers all items."""
        page1 = MagicMock()
        page1.status_code = 200
        page1.json.return_value = {
            "features": [{"id": "scene_1"}, {"id": "scene_2"}],
            "links": [{"rel": "next", "href": "https://bhoonidhi-api.nrsc.gov.in/data/search?page=2"}],
        }
        page2 = MagicMock()
        page2.status_code = 200
        page2.json.return_value = {
            "features": [{"id": "scene_3"}],
            "links": [],
        }
        mock_post.side_effect = [page1, page2]

        with patch("bhoonidhi_client.get_valid_token", return_value="mock_token"):
            results = client.search_stac(
                collections=["Sentinel-1A_SAR-IW_GRD"],
                start_date="2026-08-01",
                end_date="2026-08-20",
                bbox=[75.0, 10.0, 77.0, 12.0],
            )
            self.assertEqual(len(results), 3)
            self.assertEqual([r["id"] for r in results], ["scene_1", "scene_2", "scene_3"])

    @patch("bhoonidhi_client.requests.post")
    def test_search_stac_date_range_error_406(self, mock_post):
        """Verify 406 response translates to BhoonidhiDateRangeError."""
        mock_resp = MagicMock()
        mock_resp.status_code = 406
        mock_post.return_value = mock_resp

        with patch("bhoonidhi_client.get_valid_token", return_value="mock_token"):
            with self.assertRaises(BhoonidhiDateRangeError):
                client.search_stac(
                    collections=["Sentinel-1A_SAR-IW_GRD"],
                    start_date="2023-01-01",
                    end_date="2024-05-01",
                    bbox=[75.0, 8.0, 77.0, 10.0],
                )

    @patch("bhoonidhi_client.requests.post")
    def test_search_stac_gateway_timeout_504(self, mock_post):
        """Verify 504 response translates to BhoonidhiGatewayError."""
        mock_resp = MagicMock()
        mock_resp.status_code = 504
        mock_post.return_value = mock_resp

        with patch("bhoonidhi_client.get_valid_token", return_value="mock_token"):
            with self.assertRaises(BhoonidhiGatewayError):
                client.search_stac(
                    collections=["Sentinel-1A_SAR-IW_GRD"],
                    start_date="2026-01-01",
                    end_date="2026-01-10",
                    bbox=[75.0, 8.0, 77.0, 10.0],
                )

    @patch("bhoonidhi_client.requests.head")
    def test_file_size_mb_head_request(self, mock_head):
        """Verify HEAD request calculates file size in MB properly."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"Content-Length": "209715200"}  # 200 MB
        mock_head.return_value = mock_resp

        with patch("bhoonidhi_client.get_valid_token", return_value="mock_token"):
            sz = client.get_file_size_mb("S1A_SCENE_1", "Sentinel-1A_SAR-IW_GRD")
            self.assertEqual(sz, 200.0)

    def test_quicklook_url_extraction(self):
        """Verify quicklook URLs are parsed correctly from STAC features."""
        feat = {
            "id": "SCENE_TEST",
            "collection": "EOS-04_SAR-MRS_L2A",
            "assets": {
                "thumbnail": {"href": "https://nrsc.gov.in/thumb.jpg"}
            }
        }
        url = client.get_quicklook_url(feat)
        self.assertEqual(url, "https://nrsc.gov.in/thumb.jpg")

    def test_zip_extraction_and_raster_discovery(self):
        """Verify ZIP archives are extracted and all GeoTIFF/raster files detected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            zip_file = tmp_path / "scene_archive.zip"

            with zipfile.ZipFile(zip_file, "w") as zf:
                zf.writestr("imagery/band_vv.tif", b"FAKE_TIFF_BYTES")
                zf.writestr("imagery/band_vh.tiff", b"FAKE_TIFF_BYTES")
                zf.writestr("metadata/manifest.xml", b"<xml></xml>")

            rasters = client._extract_zip(zip_file)
            raster_names = [p.name for p in rasters]
            self.assertIn("band_vv.tif", raster_names)
            self.assertIn("band_vh.tiff", raster_names)
            self.assertNotIn("manifest.xml", raster_names)


class TestGEEVerifierEngine(unittest.TestCase):
    """Test GEE asset translation, interactive verification, and code generation."""

    def setUp(self):
        self.s1_feature = {
            "id": "S1A_IW_GRDH_1SDV_20230810T004015_20230810T004040_049806_05FD66_78A2",
            "collection": "Sentinel-1A_SAR-IW_GRD",
            "properties": {
                "datetime": "2023-08-10T00:40:15Z",
                "Online": "Y",
                "eo:cloud_cover": 0.0,
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[75.0, 10.0], [77.0, 10.0], [77.0, 12.0], [75.0, 12.0], [75.0, 10.0]]],
            }
        }
        self.eos04_feature = {
            "id": "EOS04_SAR_MRS_L2A_20230815",
            "collection": "EOS-04_SAR-MRS_L2A",
            "properties": {
                "datetime": "2023-08-15T04:30:00Z",
                "Online": "Y",
            },
        }

    def test_sentinel1_id_extraction(self):
        granule = gee.extract_sentinel1_granule_id(self.s1_feature["id"])
        self.assertEqual(granule, "S1A_IW_GRDH_1SDV_20230810T004015_20230810T004040_049806_05FD66_78A2")

    def test_gee_asset_mapping(self):
        s1_info = gee.get_gee_asset_info(self.s1_feature)
        self.assertTrue(s1_info["is_direct_gee"])
        self.assertEqual(s1_info["gee_collection"], "COPERNICUS/S1_GRD")
        self.assertEqual(
            s1_info["gee_asset_id"],
            "COPERNICUS/S1_GRD/S1A_IW_GRDH_1SDV_20230810T004015_20230810T004040_049806_05FD66_78A2"
        )

        eos_info = gee.get_gee_asset_info(self.eos04_feature)
        self.assertFalse(eos_info["is_direct_gee"])
        self.assertEqual(eos_info["access_method"], "user_asset_upload")

    def test_verification_pipeline_5_steps(self):
        res = gee.run_gee_verification(self.s1_feature, mock_mode=True)
        self.assertTrue(res["verified"])
        self.assertTrue(res["is_direct_gee"])
        self.assertEqual(len(res["steps"]), 5)
        self.assertIn("VV", res["bands"])
        self.assertIn("specular reflection", res["disaster_verdict"])

    def test_code_generators(self):
        py_code = gee.generate_gee_python_script(self.s1_feature)
        self.assertIn("ee.Initialize", py_code)
        self.assertIn("COPERNICUS/S1_GRD", py_code)
        self.assertIn("flood_water", py_code)

        js_code = gee.generate_gee_javascript_script(self.s1_feature)
        self.assertIn("ee.Image", js_code)
        self.assertIn("Map.addLayer", js_code)

        qgis_code = gee.generate_qgis_python_script(self.s1_feature)
        self.assertIn("QgsRasterLayer", qgis_code)

        cli_code = gee.generate_cli_upload_command(self.s1_feature)
        self.assertIn("earthengine upload image", cli_code)


class TestAppFeasibilityAndDefaultAOI(unittest.TestCase):
    """Test app feasibility pre-check, area calculation, and default AOI states."""

    def test_area_calculation_km2(self):
        """Verify approximate area calculation in km² for WGS84 bounding box."""
        # 1 degree lat x 1 degree lon near equator is ~111km x 111km ≈ 12,321 km²
        area = app.calc_approx_area_km2([75.0, 10.0, 76.0, 11.0])
        self.assertGreater(area, 10000)
        self.assertLess(area, 15000)

    def test_feasibility_blocked_when_no_aoi(self):
        """Verify query feasibility blocks search when AOI is None."""
        f = app.analyze_query_feasibility(
            bbox=None,
            start_date=date(2026, 9, 1),
            end_date=date(2026, 9, 10),
            mission="Sentinel-1A (Radar SAR)",
            collection="Sentinel-1A_SAR-IW_GRD",
        )
        self.assertFalse(f["can_search"])
        self.assertEqual(f["level"], "blocked")
        self.assertIn("AOI Required", f["badge"])

    def test_feasibility_blocked_on_invalid_dates(self):
        """Verify query feasibility blocks search when start_date > end_date."""
        f = app.analyze_query_feasibility(
            bbox=[75.0, 10.0, 76.0, 11.0],
            start_date=date(2026, 9, 20),
            end_date=date(2026, 9, 10),
            mission="Sentinel-1A (Radar SAR)",
            collection="Sentinel-1A_SAR-IW_GRD",
        )
        self.assertFalse(f["can_search"])
        self.assertEqual(f["level"], "blocked")

    def test_feasibility_blocked_on_date_span_over_366(self):
        """Verify query feasibility blocks date ranges exceeding 366 days."""
        f = app.analyze_query_feasibility(
            bbox=[75.0, 10.0, 76.0, 11.0],
            start_date=date(2025, 1, 1),
            end_date=date(2026, 3, 1),
            mission="Sentinel-1A (Radar SAR)",
            collection="Sentinel-1A_SAR-IW_GRD",
        )
        self.assertFalse(f["can_search"])
        self.assertIn("366-Day Cap", f["badge"])

    def test_feasibility_optimal_with_valid_parameters(self):
        """Verify optimal query feasibility when parameters are well scoped."""
        f = app.analyze_query_feasibility(
            bbox=[75.0, 10.0, 76.0, 11.0],
            start_date=date(2026, 9, 1),
            end_date=date(2026, 9, 15),
            mission="Sentinel-1A (Radar SAR)",
            collection="Sentinel-1A_SAR-IW_GRD",
        )
        self.assertTrue(f["can_search"])
        self.assertEqual(f["level"], "optimal")
        self.assertIn("Feasible", f["badge"])


if __name__ == "__main__":
    unittest.main()
