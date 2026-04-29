FROM condaforge/mambaforge:latest

WORKDIR /app

# Install geospatial C/C++ dependencies via conda-forge
RUN mamba install -y -c conda-forge \
    python=3.11 \
    gdal=3.8 \
    rasterio=1.3 \
    pyproj=3.6 \
    pdal=2.6 \
    python-pdal=3.3 \
    && mamba clean -afy

# Install pip dependencies
COPY pyproject.toml .
COPY src/ src/
RUN pip install --no-cache-dir -e ".[dev,interface]"

# Copy everything else
COPY . .

ENTRYPOINT ["salus"]
