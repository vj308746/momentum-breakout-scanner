from __future__ import annotations

import unittest

from config import STOCK_UNIVERSE_NAME
from downloader import _prepare_constituents


class StockUniverseTests(unittest.TestCase):
    def test_prepare_constituents_cleans_and_deduplicates(self) -> None:
        csv_text = (
            "Company Name,Industry,Symbol,Series\n"
            " Alpha Limited , Industrials , ALPHA ,EQ\n"
            "Beta Limited,Energy,BETA,EQ\n"
            "Alpha Duplicate,Industrials,ALPHA,EQ\n"
        )

        result = _prepare_constituents(csv_text)

        self.assertEqual(
            result["Symbol"].tolist(),
            ["ALPHA", "BETA"],
        )
        self.assertEqual(
            result["Yahoo Symbol"].tolist(),
            ["ALPHA.NS", "BETA.NS"],
        )
        self.assertTrue(
            result["Universe Source"]
            .eq(STOCK_UNIVERSE_NAME)
            .all()
        )

    def test_prepare_constituents_rejects_missing_columns(self) -> None:
        csv_text = (
            "Company Name,Symbol\n"
            "Alpha Limited,ALPHA\n"
        )

        with self.assertRaisesRegex(
            RuntimeError,
            "Industry",
        ):
            _prepare_constituents(csv_text)


if __name__ == "__main__":
    unittest.main()
