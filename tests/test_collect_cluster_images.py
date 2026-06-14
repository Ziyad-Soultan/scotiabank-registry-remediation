import json
import tempfile
import unittest
from pathlib import Path

from scripts.collect_cluster_images import build_inventory_payload, write_inventory_file


class CollectClusterImagesTests(unittest.TestCase):
    def test_build_inventory_payload_keeps_example_shape_and_dedupes_per_namespace(self):
        pod_list = {
            "items": [
                {
                    "metadata": {"namespace": "payments"},
                    "spec": {
                        "containers": [
                            {"image": "registry.corp/apps/payments-api:1.2.3"},
                            {"image": "registry.corp/apps/payments-api:1.2.3"},
                        ],
                        "initContainers": [
                            {"image": "registry.corp/base/jdk11-runtime:approved"}
                        ],
                    },
                },
                {
                    "metadata": {"namespace": "edge"},
                    "spec": {
                        "containers": [
                            {"image": "registry.corp/base/nginx:stable"},
                            {"image": "registry.corp/base/os:9.4"},
                        ],
                    },
                },
            ]
        }

        payload = build_inventory_payload(
            pod_list,
            cluster_name="prod-1",
            epm_code="gpedev",
            project_name="payments-platform",
            environment_type="prod",
        )

        self.assertEqual(payload["epm_code"], "gpedev")
        self.assertEqual(payload["project_name"], "payments-platform")
        self.assertEqual(payload["clusterName"], "prod-1")
        self.assertEqual(payload["environmentType"], "prod")
        self.assertEqual(
            payload["namespaces"],
            [
                {
                    "namespace": "edge",
                    "images": [
                        "registry.corp/base/nginx:stable",
                        "registry.corp/base/os:9.4",
                    ],
                },
                {
                    "namespace": "payments",
                    "images": [
                        "registry.corp/apps/payments-api:1.2.3",
                        "registry.corp/base/jdk11-runtime:approved",
                    ],
                },
            ],
        )

    def test_write_inventory_file_uses_dedupe_safe_cluster_filename(self):
        payload = {
            "epm_code": "gpedev",
            "clusterName": "prod east/1",
            "namespaces": [],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = write_inventory_file(payload, Path(tmpdir))
            self.assertEqual(out_path.name, "prod-east-1.images.json")
            written = json.loads(out_path.read_text())
            self.assertEqual(written["clusterName"], "prod east/1")


if __name__ == "__main__":
    unittest.main()
