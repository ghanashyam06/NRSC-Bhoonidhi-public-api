# 🛰️ ISRO Bhoonidhi & Google Earth Engine Disaster STAC Portal

An interactive Streamlit application for searching, verifying, and downloading satellite data via the **National Remote Sensing Centre (NRSC / ISRO) Bhoonidhi STAC API** with integrated **Google Earth Engine (GEE)** accessibility testing.

---

## 🚀 Key Capabilities

- **⚡ Disaster-Optimized Sensor Prioritization (Radar/SAR over Optical)**:
  - **Top Pick (Radar)**: `Sentinel-1A_SAR-IW_GRD` — cloud-penetrating Ground Range Detected SAR; water exhibits low specular backscatter (pitch black) for rapid flood and landslide delineation during monsoons.
  - **Alternative Radar**: `EOS-04_SAR-MRS_L2A/L2B` — ISRO C-band SAR sensor for Indian regional coverage.
  - **High-Res Optical**: `ResourceSat-2/2A LISS-3` (23.5m) and `AWiFS` (56m) for post-disaster damage mapping under clear skies.
  - **Default Preset**: Configured for the **Kerala / Western Ghats** monsoon disaster zone.

- **🔬 Interactive Google Earth Engine (ee.Image) Verification Workflow**:
  - Automatically translates Bhoonidhi Product / Granule IDs into GEE Asset IDs (`COPERNICUS/S1_GRD/...`).
  - Executes 5-step interactive verification testing accessibility via the `ee.Image` API.
  - Generates ready-to-run scripts for:
    - 🐍 **Google Earth Engine (Python API)** (Includes flood extent thresholding `VV < -16 dB`)
    - 🌐 **GEE Code Editor (JavaScript)** (One-click paste into `code.earthengine.google.com`)
    - 🚀 **GEE Asset Upload (CLI)** (`earthengine upload image ...`)
    - 🗺️ **QGIS Desktop & Python Script** (`iface.addRasterLayer(...)`)

- **🛡️ Robust Error-Handling Layer**:
  - Granular exception hierarchy (`BhoonidhiAuthError`, `BhoonidhiTimeoutError`, `BhoonidhiGatewayError`, `BhoonidhiRateLimitError`, `BhoonidhiDateRangeError`, `BhoonidhiNetworkError`, `BhoonidhiDownloadError`).
  - Intelligent suggestions for 502/504 gateway timeouts and large AOI queries.
  - Automatic token refresh lifecycle with backoff.

- **🗺️ Geospatial Deck & Download Manager**:
  - Full-screen Folium mapping engine with multiple basemaps (*Carto Voyager*, *Google Satellite*, *Carto Dark*, *OpenStreetMap*).
  - Multi-scene batch downloader with auto-decompression and GeoTIFF raster identification.

---

## 📋 Prerequisites & Installation

### 1. Clone & Set Up Virtual Environment

```bash
# Create virtual environment
python3 -m venv .venv

# Activate virtual environment
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Credentials

Create a `.env` file in the root directory:

```bash
cp .env.example .env
```

Edit `.env` with your Bhoonidhi credentials:

```env
BHOONIDHI_USER_ID=your_username
BHOONIDHI_PASSWORD=your_password
BHOONIDHI_BASE_URL=https://bhoonidhi-api.nrsc.gov.in
BHOONIDHI_TOKEN_URL=https://bhoonidhi-api.nrsc.gov.in/auth/token
```

> [!NOTE]
> Bhoonidhi API usernames typically do not accept hyphens (`-`) or `@` symbols.

---

## 🏃 Running the Application

Launch the Streamlit app:

```bash
streamlit run app.py
```

Open your browser at `http://localhost:8501`.

---

## 🧪 Testing & Verification Suite

Run the automated unit tests:

```bash
python test_suite.py
```

---

## 📁 Project Structure

```
.
├── app.py                 # Streamlit web application & GEE interactive UI
├── bhoonidhi_client.py    # Bhoonidhi STAC API client with robust error-handling layer
├── gee_verifier.py        # Earth Engine verification engine, sensor classification, & script generator
├── test_suite.py          # Unit tests for error handling & GEE verification
├── auth_test.py           # Standalone authentication test script
├── auth_refresh_test.py   # Token refresh workflow verification test
├── requirements.txt       # Python package dependencies
├── .env.example           # Template for environment variables
└── downloads/             # Target directory for downloaded satellite scenes
```
