import unittest

from scripts.deduplicate_image_records import aggregate_records, expand_runtime_inventory_input


class DeduplicateImageRecordsTests(unittest.TestCase):
    def test_expand_runtime_inventory_preserves_cluster_and_workload_metadata(self):
        payload = {
            "epm_code": "gpedev",
            "project_name": "payments-platform",
            "clusterName": "prod-1",
            "environmentType": "prod",
            "namespaces": [
                {
                    "namespace": "payments",
                    "images": [
                        {
                            "image": "registry.corp/base/jdk11-runtime:approved",
                            "workloadKind": "Deployment",
                            "workloadName": "payments-api",
                            "appName": "payments",
                            "appInstance": "payments-prod",
                            "component": "api",
                            "partOf": "card-platform",
                            "managedBy": "helm",
                            "podName": "payments-api-abcde",
                            "containerName": "certs",
                            "containerType": "initContainer",
                        },
                        {
                            "image": "registry.corp/base/jdk11-runtime:approved",
                            "workloadKind": "Deployment",
                            "workloadName": "payments-api",
                            "appName": "payments",
                            "appInstance": "payments-prod",
                            "component": "api",
                            "partOf": "card-platform",
                            "managedBy": "helm",
                            "podName": "payments-api-fghij",
                            "containerName": "certs",
                            "containerType": "initContainer",
                        },
                    ],
                }
            ],
        }

        records = expand_runtime_inventory_input(payload)

        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]["clusterName"], "prod-1")
        self.assertEqual(records[0]["ownerTeam"], "gpedev")
        self.assertEqual(records[0]["workloadKind"], "Deployment")
        self.assertEqual(records[0]["workloadName"], "payments-api")
        self.assertEqual(records[0]["appName"], "payments")
        self.assertEqual(records[0]["appInstance"], "payments-prod")
        self.assertEqual(records[0]["podName"], "payments-api-abcde")
        self.assertEqual(records[0]["containerName"], "certs")
        self.assertEqual(records[0]["metadata"]["epmCode"], "gpedev")

    def test_aggregate_records_keeps_cross_cluster_sightings_under_one_key(self):
        records = [
            {
                "image": "registry.corp/base/jdk11-runtime:approved",
                "sourceType": "cluster",
                "sourceName": "payments-platform",
                "environmentType": "prod",
                "clusterName": "prod-1",
                "namespace": "payments",
                "workloadKind": "Deployment",
                "workloadName": "payments-api",
                "podName": "payments-api-abcde",
                "containerName": "api",
                "ownerTeam": "gpedev",
                "appName": "payments",
                "appInstance": "payments-prod",
            },
            {
                "image": "registry.corp/base/jdk11-runtime:approved",
                "sourceType": "cluster",
                "sourceName": "payments-platform",
                "environmentType": "prod",
                "clusterName": "prod-2",
                "namespace": "payments",
                "workloadKind": "Deployment",
                "workloadName": "payments-api",
                "podName": "payments-api-fghij",
                "containerName": "api",
                "ownerTeam": "gpedev",
                "appName": "payments",
                "appInstance": "payments-prod",
            },
        ]

        unique_images, sightings, summary = aggregate_records(records)

        self.assertEqual(len(unique_images), 1)
        self.assertEqual(unique_images[0]["clusters"], ["prod-1", "prod-2"])
        self.assertEqual(unique_images[0]["sightingCount"], 2)
        self.assertEqual(unique_images[0]["workloads"][0]["containerName"], "api")
        self.assertEqual(unique_images[0]["apps"][0]["appName"], "payments")
        self.assertEqual(len(sightings[unique_images[0]["canonicalKey"]]), 2)
        self.assertEqual(sightings[unique_images[0]["canonicalKey"]][0]["podName"], "payments-api-abcde")
        self.assertEqual(summary["inputRecordCount"], 2)
        self.assertEqual(summary["uniqueImageCount"], 1)


if __name__ == "__main__":
    unittest.main()
