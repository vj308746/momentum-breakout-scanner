from __future__ import annotations

import unittest
from unittest.mock import patch

import pandas as pd

from downloader import download_stock_data


class DownloaderFallbackTests(unittest.TestCase):
    @patch("downloader.DATA_SOURCE", "upstox")
    @patch("downloader.ALLOW_YAHOO_FALLBACK", True)
    @patch("downloader._download_yahoo_data")
    @patch("downloader.download_upstox_stock_data")
    def test_upstox_key_uses_explicit_yahoo_fallback(
        self,
        upstox_download,
        yahoo_download,
    ) -> None:
        upstox_download.side_effect = RuntimeError("temporary failure")
        yahoo_download.return_value = pd.DataFrame({"Close": [1.0]})

        result = download_stock_data(
            "NSE_EQ|INE169A01031",
            yahoo_fallback_symbol="COROMANDEL.NS",
        )

        yahoo_download.assert_called_once_with("COROMANDEL.NS")
        self.assertFalse(result.empty)


if __name__ == "__main__":
    unittest.main()
