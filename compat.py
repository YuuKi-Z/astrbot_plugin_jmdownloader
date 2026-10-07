"""Accept a UTF-8 BOM from JM's API without changing global API clients.

On the target server, current API responses start with U+FEFF. jmcomic 2.7.7
rejects these before JSON parsing. A client subclass normalises only API text;
upstream status checks, image responses and retry handling remain in charge.
"""

import json

from jmcomic import JmApiClient, JmModuleConfig


class ApiResponseView:
    def __init__(self, response):
        self.response = response

    @property
    def text(self):
        return self.response.text.lstrip("\ufeff \t\r\n")

    def json(self, **kwargs):
        return json.loads(self.text, **kwargs)

    def __getattr__(self, name):
        return getattr(self.response, name)


class CompatibleJmApiClient(JmApiClient):
    client_key = "astrbot_jm_api"

    def raise_if_resp_should_retry(self, response, is_image):
        if not is_image and "\ufeff" in response.text[:8]:
            response = ApiResponseView(response)
        return super().raise_if_resp_should_retry(response, is_image)


def register_compatible_client() -> str:
    JmModuleConfig.register_client(CompatibleJmApiClient)
    return CompatibleJmApiClient.client_key
