import unittest

from scripts.scan_unique_images import match_family
from scripts.trivy_to_scan_metadata import count_findings


class ScanUniqueImagesTests(unittest.TestCase):
    def test_match_family_supports_requested_base_families(self):
        catalog = {
            "families": [
                {"name": "os", "selectors": {"imageRegexes": [".*(/|-)os([:-]|$).*"]}},
                {"name": "python", "selectors": {"imageRegexes": [".*python.*"]}},
                {"name": "jdk-11", "selectors": {"imageRegexes": [".*jdk[-._]?11.*", ".*openjdk[-._]?11.*"]}},
                {"name": "jdk-8", "selectors": {"imageRegexes": [".*jdk[-._]?8.*", ".*openjdk[-._]?8.*"]}},
                {"name": "jdk-25", "selectors": {"imageRegexes": [".*jdk[-._]?25.*", ".*openjdk[-._]?25.*"]}},
                {"name": "jre-8", "selectors": {"imageRegexes": [".*jre[-._]?8.*"]}},
                {"name": "jre-11", "selectors": {"imageRegexes": [".*jre[-._]?11.*"]}},
                {"name": "jre-25", "selectors": {"imageRegexes": [".*jre[-._]?25.*"]}},
                {"name": "nginx", "selectors": {"imageRegexes": [".*nginx.*"]}},
            ]
        }

        cases = {
            "registry.corp/base/os:9.4": "os",
            "registry.corp/base/python-311:approved": "python",
            "registry.corp/base/jdk11-runtime:approved": "jdk-11",
            "registry.corp/base/jdk8-runtime:approved": "jdk-8",
            "registry.corp/base/jdk25-runtime:approved": "jdk-25",
            "registry.corp/base/jre8-runtime:approved": "jre-8",
            "registry.corp/base/jre11-runtime:approved": "jre-11",
            "registry.corp/base/jre25-runtime:approved": "jre-25",
            "registry.corp/base/nginx:stable": "nginx",
        }

        for image, expected in cases.items():
            with self.subTest(image=image):
                family = match_family({"normalizedImageName": image}, catalog)
                self.assertEqual(family["name"], expected)

    def test_count_findings_keeps_only_high_and_critical(self):
        report = {
            "Results": [
                {
                    "Target": "usr/lib/python3.11/site-packages",
                    "Class": "lang-pkgs",
                    "Type": "pip",
                    "Vulnerabilities": [
                        {"Severity": "CRITICAL", "FixedVersion": "1.2.3"},
                        {"Severity": "HIGH", "FixedVersion": "1.2.4"},
                        {"Severity": "MEDIUM", "FixedVersion": "1.2.5"},
                    ],
                }
            ]
        }

        counts = count_findings(report)

        self.assertEqual(counts["criticalCount"], 1)
        self.assertEqual(counts["highCount"], 1)
        self.assertEqual(counts["fixableCriticalCount"], 1)
        self.assertEqual(counts["fixableHighCount"], 1)
        self.assertEqual(counts["targetClasses"], ["python"])


if __name__ == "__main__":
    unittest.main()
