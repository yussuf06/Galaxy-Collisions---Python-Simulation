"""Choose the real GPU view; headless regression runs explicitly use software."""
import os

if os.environ.get('QT_QPA_PLATFORM', '').lower() in ('offscreen', 'minimal'):
    from .view import GalaxyView
else:
    from .gpu_view import GalaxyView
