from __future__ import annotations

import unittest

from swiss_jobs.providers.linked_in.client import LinkedInHttpClient, _normalize_proxy_url


class LinkedInClientTests(unittest.TestCase):
    def test_client_builds_safe_default_search_params(self) -> None:
        client = LinkedInHttpClient()
        params = client._build_query_params(  # noqa: SLF001
            mode="search",
            term="software engineer",
            location="Zurich, Switzerland",
            page=2,
        )

        self.assertEqual("software engineer", params["keywords"])
        self.assertEqual("Zurich, Switzerland", params["location"])
        self.assertEqual("25", params["start"])
        self.assertEqual("DD", params["sortBy"])

    def test_proxy_host_port_login_password_format_is_normalized(self) -> None:
        proxy_url = _normalize_proxy_url("gw.example.com:10002:user;city.zurich:secret")

        self.assertEqual("http://user%3Bcity.zurich:secret@gw.example.com:10002", proxy_url)


if __name__ == "__main__":
    unittest.main()

