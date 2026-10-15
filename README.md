# REPROVEX

**A GenLayer-native adversarial testing, execution diagnosis and consensus-backed bug bounty workspace.**

REPROVEX provides an independent record of contract specifications, source-pinned verification, actual GenVM traces, evidence challenges, semantic validator agreement, and escrow consequences. This is a **developer tooling product**: Portal category **Developer Tools**, tags **Contract Testing** and **Failure Diagnosis**.

## Deploy target and exact software choices

| Item | Configured value |
| --- | --- |
| GenLayer network | **Studionet / 61999** |
| Canonical RPC | `https://studio.genlayer.com/api` |
| Explorer | `https://explorer-studio.genlayer.com` |
| GenLayer CLI | **repository-local `genlayer@0.39.1`** (`package.json`) |
| GenVM | Exact runtime `py-genlayer` hash from the first line of each contract |
| TypeScript client | `genlayer-js@1.1.8` |
| Wallet | Injected EIP-1193 provider; no WalletConnect, Privy or Snaps |
| Application | Next.js 15 App Router, React 19, TypeScript |

The canonical Studionet deployment is recorded in `deployments/studionet.json`. This workspace targets stable Studionet only; it does not silently use the 61997 release candidate.

## Product map

- `contracts/spec_registry.py`: immutable target/source/specification registrations, SHA-256 commitments, owner-controlled successors, bounded suite pagination.
- `contracts/verification_market.py`: sponsor-funded bounties, tester-backed claims, sponsor counterevidence windows, independent validator assessments, duplicate-transaction protection, expiry refunds, pull credits and finalized EVM value dispatch.
- `runner/reprovex.py`: real GenLayer RPC inspection and AST inspection, source hash verification, adversarial test definitions, official test execution (`run`) and RPC health.
- `frontend/`: mobile-responsive workspace with six views: overview, specifications, bounty campaigns, challenge docket, authoritative transaction diagnostics and adversarial test lab. All on-chain data originates from contract reads; mock fixtures are labeled explicitly as test *definitions*, not passed results.
- `tests/unit/`: isolated, deterministic ledger/security tests with a simulated GenLayer context. **Not GenVM equivalence or network proof.**
- `tests/direct/`: official `genlayer-test` Direct Mode tests, requiring the GenVM SDK.
- `.github/workflows/verify.yml`: static and semantic lint, actual SDK Direct Mode, isolated unit tests, pinned CLI check, TypeScript and production build gates.

## Security and consensus model

1. A suite pins an already deployed GenLayer source file and behavior specification to two **immutable full-commit raw GitHub URLs** and exact SHA-256 digests. No trust is placed in mutable `main` or server-side copies.
2. The suite owner creates a payable bounty with a precommitted test stake, deadline and **15-minute to 24-hour** counterevidence interval.
3. A distinct tester bonds a report against a transaction hash, plus a commit-pinned reproduction manifest. The sponsor may file **one** immutable counterevidence bundle before the response window ends.
4. During a `resolve_case` transaction, each validator independently retrieves the pinned source, specification, manifest and counterevidence, plus the *actual finalized* deployed source, receipt and execution trace from the GenLayer RPC.
5. The evaluation is evidence-first and fail closed: missing source, mismatched digest, nonfinal receipt, mismatched contract, missing trace, malformed model output and material validator disagreement never produce a payable bug verdict.
6. The leader and validators must agree on **verdict, severity, failure class, violated specification rule, evidence-validity and the evidence proof root**. Textual explanations are nonauthorizing. `CONFIRMED` requires an applicable **HIGH** or **CRITICAL** rule violation. A mere error or allegation is insufficient.
7. A confirmed finding credits the independent tester with the stake and bounty, and closes the campaign. An unsupported rejected challenge credits the stake to the sponsor. An inconclusive outcome returns the stake; the bounty stays open. A transaction can earn only one reward across campaigns. The sponsor can reclaim unused bounties after their deadline once no unresolved case is active.
8. Credits are withdrawn separately: effects happen before one EVM value transfer scheduled on finality. Budget the additional message fee during live fee profiling; `dispatched` tracks scheduled withdrawals, *not independent proof that a recipient received funds*. Cross-chain/external-message finality must be checked live.

**Trust and availability limits:** Pinning a GitHub source proves what its exact bytes were; it does not establish who authored the code. A public transaction trace proves execution output only to the extent the node returns authentic finalized data; logs and reproduction manifests are treated as adversarial text. The RPC debug endpoint might not be available to a particular GenVM validator. If so, a case becomes `INCONCLUSIVE` rather than paying. A diagnostic observation is not a consensus verdict. Current deployed-source parity is checked at resolution time; upgraded targets will not match the pinned suite and require a new suite/snapshot. The GenLayer native appeal window still controls final settlement. These are deliberately documented trust boundaries, not simulated proof.

## Installation

Use Python 3.12+, Node 22+, a funded Studionet CLI account and your own injected browser wallet. **No Docker is needed to run Direct Mode** or the hosted Studionet frontend.

```bash
cd REPROVEX
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
npm install --ignore-scripts
npm --prefix frontend install
```

The root `npm install` installs `genlayer@0.39.1` locally. Always invoke `./node_modules/.bin/genlayer` (deployment script adds that directory to `PATH`); **never rely on a global newer GenLayer CLI.**

## Verification gates

```bash
python -m pytest tests/unit -v
python -m pytest tests/direct -v  # real GenLayer Direct Mode, not the simulated unit suite
REGISTRY_ADDRESS=0x... MARKET_ADDRESS=0x... VERIFIED_TX_HASH=0x... python -m pytest tests/integration -v
bash scripts/lint-contracts.sh  # AST + SDK semantic validation
python scripts/preflight.py  # hard-fail on missing native tooling, RPC, chain or real GenVM schema
python runner/reprovex.py inspect contracts/spec_registry.py contracts/verification_market.py
python runner/reprovex.py run tests/direct
python runner/reprovex.py health  # calls the actual hosted GenLayer RPC
npm --prefix frontend run typecheck
npm --prefix frontend run build
```

The script `scripts/verify-remote-deployment.py` checks **finalized deployed code byte-for-byte** against the two contract files once genuine addresses are available. Do not treat green isolated unit tests as proof of `genvm-lint check`, actual Direct Mode, network acceptance/finality, deployed bytes or UX integration; all those must pass separately.

## Deployment on canonical Studionet

**Before deploying:** Require a passing `python scripts/preflight.py` (all real GenVM schemas and network checks); run both semantic checks and official Direct Mode against the actual SDK; make sure the CLI account and wallet both have sufficient GEN for network fees. Source can be verified locally without signing.

```bash
npm install --ignore-scripts
bash scripts/deploy-studionet.sh
```

This deploys **SpecRegistry**. Obtain its **finalized** address and transaction hash from the real CLI/explorer output; then, only after verifying the finalized result, run:

```bash
REGISTRY_ADDRESS=0xYOUR_FINALIZED_SPEC_REGISTRY_ADDRESS bash scripts/deploy-studionet.sh
```

That deploys **VerificationMarket** with the SpecRegistry address as its constructor argument. Wait for successful finalized execution, not mere submission or acceptance. Capture the market address.

```bash
REGISTRY_ADDRESS=0x... MARKET_ADDRESS=0x... python scripts/verify-remote-deployment.py
cp frontend/.env.example frontend/.env.local
# Set the two verified addresses in frontend/.env.local
npm --prefix frontend run dev
```

When deploying the Next.js application to Vercel, set `NEXT_PUBLIC_REGISTRY_ADDRESS` and `NEXT_PUBLIC_MARKET_ADDRESS` in the frontend project's deployment environment and use `frontend` as the root directory. Do not put private keys in environment variables for the browser or commit `.env.local`.

## First genuinely verifiable lifecycle

1. Register a suite containing a specific target deployed to 61999, an immutable raw source URL and SHA, a *versioned, testable, rule-ID* specification document and SHA, and a summary of its intended behavior.
2. Sponsor the suite with a real payable GEN bounty, a challenge-bond minimum, a deadline at least 24h out and a response window between 900 and 86400 seconds.
3. Run malicious/negative/positive scenarios against that target **using actual Direct Mode or real network transactions**. A transaction used for on-chain bounty verification must exist, target the registered contract and already be finalized; copying example placeholders will not pass.
4. Publish a reproduction manifest as a file in a commit-addressed public GitHub revision. Copy its raw URL and SHA-256 into the bonded case form. The claimant must use a different wallet than the sponsor.
5. Submit one sponsor rebuttal if applicable. Resolve after the precommitted response deadline. Inspect `proof_root`, `failure_class`, severity and the contract view results.
6. Allow GenLayer consensus finality, inspect transaction receipts, withdraw any credited bounty/stake, then independently check sender and recipient balances and the EVM transfer result. Try malicious duplicate and unauthorized requests and save their on-chain receipts.
7. Exercise the entire process through the live, hosted UI from a genuine EIP-1193 wallet, including wrong network, rejection, refresh, resumed tx finality, unavailable RPC, missing evidence and resolution without a bounty payout.

## References

- GenLayer CLI 0.39.1: https://docs.genlayer.com/api-references/genlayer-cli
- GenLayer SDK client/wallet/finality/fees: https://docs.genlayer.com/api-references/genlayer-js
- Contract fee separation and transfers: https://docs.genlayer.com/developers/intelligent-contracts/features/value-transfers
- GenLayer Direct Mode testing: https://docs.genlayer.com/api-references/genlayer-test
- GenVM safety and SDK checks: https://docs.genlayer.com/api-references/genlayer-linter
- RPC documented receipt / trace / code surfaces: https://docs.genlayer.com/api-references/genlayer-node

## Scope statement

REPROVEX includes no fabricated results or simulated production contract integration. The two contracts recorded in `deployments/studionet.json` were deployed through real Studionet consensus and checked for exact source parity. Test manifests remain templates, and the lab's ten scenarios are test *plans* until executed. Run a real economic lifecycle and hosted browser validation before representing the complete bounty lifecycle as verified.
