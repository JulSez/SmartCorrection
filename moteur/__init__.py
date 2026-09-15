"""SmartCorrection engine package."""

# GUI workflow refinements are installed as method patches on workflow v2.
from . import pr17_patch as _pr17_patch  # noqa: F401,E402
from . import pr18_patch as _pr18_patch  # noqa: F401,E402
from . import pr18_compat as _pr18_compat  # noqa: F401,E402
from . import pr20_patch as _pr20_patch  # noqa: F401,E402
