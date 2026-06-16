import json
import tempfile
import unittest
from pathlib import Path

from scripts.collect_cluster_images import build_inventory_payload, write_inventory_file


class CollectClusterImagesTests(unittest.TestCase):
    def test_build_inventory_payload_preserves_workload_and_container_context(self):
        pod_list = {
            "items": [
                {
                    "metadata": {
                        "name": "payments-api-7d9c6d9bb8-qwert",
                        "namespace": "payments",
                        "labels": {
                            "app.kubernetes.io/name": "payments",
                            "app.kubernetes.io/instance": "payments-prod",
                            "app.kubernetes.io/component": "api",
                            "app.kubernetes.io/part-of": "card-platform",
                            "app.kubernetes.io/managed-by": "helm",
                        },
                        "ownerReferences": [
                            {"controller": True, "kind": "ReplicaSet", "name": "payments-api-7d9c6d9bb8"}
                        ],
                    },
                    "spec": {
                        "containers": [
                            {"name": "api", "image": "registry.corp/apps/payments-api:1.2.3"},
                            {"name": "api", "image": "registry.corp/apps/payments-api:1.2.3"},
                        ],
                        "initContainers": [
                            {"name": "certs", "image": "registry.corp/base/jdk11-runtime:approved"}
                        ],
                    },
                },
                {
                    "metadata": {
                        "name": "edge-web-0",
                        "namespace": "edge",
                        "ownerReferences": [
                            {"controller": True, "kind": "StatefulSet", "name": "edge-web"}
                        ],
                    },
                    "spec": {
                        "containers": [
                            {"name": "nginx", "image": "registry.corp/base/nginx:stable"},
                            {"name": "os", "image": "registry.corp/base/os:9.4"},
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
                        {
                            "image": "registry.corp/base/nginx:stable",
                            "containerName": "nginx",
                            "containerType": "container",
                            "podName": "edge-web-0",
                            "workloadKind": "StatefulSet",
                            "workloadName": "edge-web",
                            "appName": "edge-web",
                        },
                        {
                            "image": "registry.corp/base/os:9.4",
                            "containerName": "os",
                            "containerType": "container",
                            "podName": "edge-web-0",
                            "workloadKind": "StatefulSet",
                            "workloadName": "edge-web",
                            "appName": "edge-web",
                        },
                    ],
                },
                {
                    "namespace": "payments",
                    "images": [
                        {
                            "image": "registry.corp/apps/payments-api:1.2.3",
                            "containerName": "api",
                            "containerType": "container",
                            "podName": "payments-api-7d9c6d9bb8-qwert",
                            "workloadKind": "Deployment",
                            "workloadName": "payments-api",
                            "appName": "payments",
                            "appInstance": "payments-prod",
                            "component": "api",
                            "partOf": "card-platform",
                            "managedBy": "helm",
                        },
                        {
                            "image": "registry.corp/base/jdk11-runtime:approved",
                            "containerName": "certs",
                            "containerType": "initContainer",
                            "podName": "payments-api-7d9c6d9bb8-qwert",
                            "workloadKind": "Deployment",
                            "workloadName": "payments-api",
                            "appName": "payments",
                            "appInstance": "payments-prod",
                            "component": "api",
                            "partOf": "card-platform",
                            "managedBy": "helm",
                        },
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
