"""Multi-mission Solar Image Analysis backend.

Pure NumPy/SunPy/astropy modules ported (near-verbatim) from the e-CALLISTO FITS
Analyzer desktop app's ``src/Backend`` — the acquisition layer (``sunpy_archive``,
``jsoc_client``, ``lasco_ingest``, ``suvi_ingest``, ``instrument_profiles``) and the
science layer (``coronagraph``, ``solar_grid``, ``image_measure``, ``sunpy_analysis``,
``hi_jmap``, ``hmi_vector_field``, ``multiview``, ``helioviewer``, ``solar_session``,
``solar_data_analysis``). No Qt imports; SunPy/astropy are imported lazily inside
functions so importing this package never requires the ``[sci]`` extra.

These modules are consumed by the FastAPI Data Analysis services
(``app.services.aia_data_service`` / ``app.services.aia_analysis_service``) and router
(``app.api.routes_data_analysis``).
"""
