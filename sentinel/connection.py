"""
Cognee Cloud connection — call setup_cognee() once at startup before any cognee operations.
"""

import os
import cognee


async def setup_cognee() -> None:
    cloud_url = os.environ["COGNEE_CLOUD_URL"]
    cloud_key = os.environ["COGNEE_CLOUD_API_KEY"]
    await cognee.serve(url=cloud_url, api_key=cloud_key)