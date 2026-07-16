"""Run the full data refresh, then rebuild the dashboard.

Each step is isolated so one network failure (e.g. a single data source down)
doesn't abort the rest. Intended for the weekly GitHub Actions job.
"""
import importlib


STEPS = ["refresh_holdings", "refresh_prices", "refresh_trials", "build_dashboard"]


def main():
    for name in STEPS:
        print("\n=== %s ===" % name)
        try:
            mod = importlib.import_module(name)
            (mod.main if hasattr(mod, "main") else mod.build)()
        except Exception as e:  # noqa
            print("!! %s failed: %s (continuing)" % (name, e))


if __name__ == "__main__":
    main()
