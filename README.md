# ore

The Ore agent system — a monorepo of services.

| Service                | Language | Role                                                  |
| ---------------------- | -------- | ----------------------------------------------------- |
| [`ore-stt`](./ore-stt) | Python   | Speech-to-text daemon. Audio bytes → transcript (gRPC). |

CI runs per-service via path-filtered GitHub Actions workflows in
[`.github/workflows/`](./.github/workflows).
