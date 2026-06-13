# Fuel Optimization API

A high-performance Django REST API designed to optimize fuel stops for long-distance vehicle routes. By integrating spatial data and dynamic programming, this service identifies the most cost-effective fueling strategy, significantly reducing operational expenses for logistics and trucking.

## Key Features

- **Global Minimum Optimization**: Uses a Dynamic Programming (DP) algorithm to find the absolute lowest cost for a journey. Unlike greedy approaches, it evaluates the entire route to ensure that every fuel stop decision contributes to the overall minimum expenditure.
- **Detour Cost Awareness**: Accurately accounts for the distance and time lost when exiting a highway to reach a fuel stop. The optimization algorithm incorporates "in-and-out" detour mileage into the total cost and range calculations.
- **Efficient Spatial Search**: Leverages a **KD-Tree** (K-Dimensional Tree) for ultra-fast proximity queries. Fuel stops are indexed once and queried against a simplified route (using the Ramer-Douglas-Peucker algorithm) to minimize computational overhead.
- **Smart Caching**: Implements multi-level caching for geocoding (Nominatim), routing (OSRM), and spatial data to ensure sub-second response times for recurring requests.

## Installation

1. **Clone the repository**:
   ```bash
   git clone https://github.com/milos-plavsic/Django-Api-for-Fuel-Optimization.git
   cd Django-Api-for-Fuel-Optimization
   ```

2. **Set up a virtual environment**:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Initialize Database**:
   ```bash
   python manage.py migrate
   ```

5. **Import Fuel Stop Data**:
   Ensure you have a CSV or source for fuel stops, then use the provided management command (if available) or import via script.

6. **Run the server**:
   ```bash
   python manage.py runserver
   ```

## Usage Diagnostic Tool

A professional diagnostic tool is included to test the API logic directly from the CLI:

```bash
python demo_api.py --start "Nashville, TN" --finish "Dallas, TX" --mpg 6.5 --capacity 150
```

## Technical Architecture

- **Backend**: Django 5.0+ with Django REST Framework.
- **Data Science Stack**: NumPy and SciPy for spatial indexing and numerical calculations.
- **Routing**: Open Source Routing Machine (OSRM).
- **Geocoding**: OpenStreetMap (Nominatim).

---
*Developed with a focus on production-grade performance and architectural scaling.*
