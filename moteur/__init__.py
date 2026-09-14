"""SmartCorrection engine package."""

# GUI workflow refinements are installed as method patches on workflow v2. Keeping
# them in a separate module makes the UX fix easy to review and remove later.
from . import pr17_patch as _pr17_patch  # noqa: F401,E402
