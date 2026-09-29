# AWS setup (live mode)

Local demo mode needs none of this (`MOCK_BEDROCK=true`). This page is for live mode: Bedrock as the host model,
AgentCore, Polly, and (P1) a Knowledge Base on S3 Vectors. Never OpenSearch Serverless (CLAUDE.md Rule 1).

Rules for this setup: no root access keys; no long-term access keys at all (the CLI uses IAM Identity Center
short-lived credentials); secrets never go into chat, the repo, or `.env.example`.

## 1. Region check (2026-09-28, from AWS docs)

| Service we plan to use | us-east-1 (N. Virginia) | us-west-2 (Oregon) | ap-south-1 (Mumbai) | Source |
|---|---|---|---|---|
| Claude Sonnet 5 on Bedrock | **in-Region**, Geo, Global | Geo, Global | Global only | [1] |
| Claude Opus 5.5 on Bedrock | **in-Region**, Geo, Global | Geo, Global | Global only | [1] |
| Claude Fable 5.1 on Bedrock | Geo, Global | Geo, Global | Global only | [1] |
| Amazon Nova Lite | in-Region, Geo | in-Region, Geo | Geo only | [1] |
| Titan Text Embeddings V2 (Knowledge Base embeddings) | in-Region | in-Region | in-Region | [1], [2] |
| AgentCore Runtime, Memory, Gateway, Identity, Observability, Policy, Evaluations | all ✓ | all ✓ | all ✓ | [3] |
| Amazon S3 Vectors | ✓ | ✓ | ✓ | [4] |
| Polly neural voices (en-IN Kajal; no Telugu voice exists) | ✓ | ✓ | ✓ | [5], [6] |

"Geo" = cross-Region inference within one geography (e.g. US); "Global" = global cross-Region inference. With
cross-Region inference, "your data can be shared across Regions" [2].

Not yet confirmed from docs (checked in the account instead, section 4): Bedrock Guardrails per-Region support (the
Guardrails page now points to per-model cards), Knowledge Bases with S3 Vectors as the vector store per Region, and
Claude Haiku 4.5 (not in the Regional availability table as fetched).

**Recommendation: us-east-1.** It is the only one of the three where the Claude models we would use run in-Region
(no cross-Region data movement for the host model), and it has every AgentCore feature, S3 Vectors, Titan
embeddings and Polly Kajal. ap-south-1 is closer to Indian farmers and has every service, but Claude there runs only
through Global cross-Region inference, so requests leave the Region anyway. Revisit if a real deployment for Indian
farmers needs data residency.

Sources (fetched 2026-09-28):
1. Bedrock Regional availability: https://docs.aws.amazon.com/bedrock/latest/userguide/models-region-compatibility.html
2. Knowledge Base models and Regions: https://docs.aws.amazon.com/bedrock/latest/userguide/knowledge-base-supported.html
3. AgentCore supported Regions: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/agentcore-regions.html
4. S3 Vectors Regions: https://docs.aws.amazon.com/AmazonS3/latest/userguide/s3-vectors-regions-quotas.html
5. Polly available voices: https://docs.aws.amazon.com/polly/latest/dg/available-voices.html
6. Polly neural voice Regions: https://docs.aws.amazon.com/polly/latest/dg/neural-voices.html

## 2. Account plan first (console)

AWS accounts are on a **Free** or **Paid** plan [7]. On the Free plan: "Access to select AWS services and features",
no "certain AWS Marketplace offers that can incur charges", "Not eligible for other promotional credits", and the
account closes when credits run out or after six months [7]. Anthropic models on Bedrock are bought through AWS
Marketplace and need "a valid payment method ... for AWS Marketplace purchases" [8]. Joining AWS Organizations
(needed for the recommended CLI identity, step 3) upgrades a Free-plan account to Paid automatically [7].

Check: Billing and Cost Management console home shows the plan and the credit balance [7]. Upgrading is a
billing decision for the account owner; budget alerts notify, they do not cap spending.

7. Choosing a plan: https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/free-tier-plans.html
8. Bedrock model access: https://docs.aws.amazon.com/bedrock/latest/userguide/model-access.html

## 3. CLI identity: IAM Identity Center (no access keys)

Only an organization instance gives "single sign-on access to your AWS accounts" [9]; an account instance cannot.

1. Console (root user, MFA): enable IAM Identity Center in **us-east-1** as an **organization instance**. This
   creates an AWS Organization with the account as management account [9].
2. Create one user for yourself (not root). Enable MFA for it.
3. Create a permission set `CluckTalkVerify` with these AWS managed policies (verification phase only):
   `AmazonBedrockFullAccess` [10], `AmazonPollyReadOnlyAccess` [11], `ServiceQuotasReadOnlyAccess` [12].
   Plus this **inline policy**: three read-only billing actions so the CLI can confirm the account plan, credits and
   seller of record (names as in the AWS managed policy `AWSBillingReadOnlyAccess` [16]), and a Deny on the Bedrock
   actions that can cost a lot at once (all six are Bedrock API operations [15]). The permission-set editor flags any
   action name it does not recognise. The same JSON is in `docs/clucktalk-verify-inline-policy.json` (copy-paste
   source; keep the two identical).

   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Sid": "ReadAccountPlanAndCredits",
         "Effect": "Allow",
         "Action": [
           "freetier:GetAccountPlanState",
           "billing:GetCredits",
           "billing:GetSellerOfRecord"
         ],
         "Resource": "*"
       },
       {
         "Sid": "NoLargeBedrockSpend",
         "Effect": "Deny",
         "Action": [
           "bedrock:CreateProvisionedModelThroughput",
           "bedrock:CreateModelCustomizationJob",
           "bedrock:CreateModelInvocationJob",
           "bedrock:CreateModelImportJob",
           "bedrock:CreateCustomModelDeployment",
           "bedrock:CreateMarketplaceModelEndpoint"
         ],
         "Resource": "*"
       }
     ]
   }
   ```

   Session duration: 4 hours. This is narrower than the `PowerUserAccess` the CLI guide suggests [13]; deploy
   permissions (CDK, AgentCore) get their own reviewed permission set later.
4. Assign the user + permission set to the account.

9. Identity Center instance types: https://docs.aws.amazon.com/singlesignon/latest/userguide/identity-center-instances.html
10. https://docs.aws.amazon.com/aws-managed-policy/latest/reference/AmazonBedrockFullAccess.html
11. https://docs.aws.amazon.com/aws-managed-policy/latest/reference/AmazonPollyReadOnlyAccess.html
12. https://docs.aws.amazon.com/aws-managed-policy/latest/reference/ServiceQuotasReadOnlyAccess.html
13. CLI with Identity Center: https://docs.aws.amazon.com/cli/latest/userguide/sso-configure-profile-token.html
15. Bedrock API operations: https://docs.aws.amazon.com/bedrock/latest/APIReference/API_Operations_Amazon_Bedrock.html
16. https://docs.aws.amazon.com/aws-managed-policy/latest/reference/AWSBillingReadOnlyAccess.html

### Accounts sold by AWS India (AISPL)

Checked 2026-09-28. AWS India accounts are billed in INR and paid manually each month unless e-mandate is on; "AWS
Marketplace purchases and subscription charges ... must be paid manually on the Payments page" [17]. Claude models are
"third-party models that AWS delivers through AWS Marketplace"; on an AWS India account, RBI rules on stored cards mean
that with a credit or debit card as the default payment method "your Marketplace subscription can fail and model
access isn't turned on". Fix: make **Pay by Invoice** the default, or pay the Marketplace subscription manually on the
Payments page **within one hour** [18]. Anthropic lists India as a supported country for the API [19]. No AWS page
found states an AISPL difference for IAM Identity Center or for redeeming promotional credits, and none states whether
promotional credits cover Marketplace-billed Bedrock models (see each credit's "Applicable products" in the Billing
console [20]). Amazon's own models (e.g. Nova) are not sold through AWS Marketplace [8], so they are the fallback host
model if the Claude subscription is blocked.

17. AWS India account differences: https://repost.aws/knowledge-center/aws-india-differences
18. Turn on Anthropic models on Bedrock (AWS India section): https://repost.aws/knowledge-center/bedrock-access-anthropic-model
19. Anthropic supported countries: https://www.anthropic.com/supported-countries
20. Applying AWS credits: https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/useconsolidatedbilling-credits.html

## 4. AWS CLI on Windows

Install (current user, no admin) [14]: download and run `https://awscli.amazonaws.com/AWSCLIV2-User.msi`, then open
a **new** cmd window:

```
aws --version
aws configure sso
    SSO session name: clucktalk
    SSO start URL:    (the AWS access portal URL from Identity Center)
    SSO region:       us-east-1
    SSO registration scopes: sso:account:access
    (browser opens: sign in as your Identity Center user, approve)
    Default client Region: us-east-1
    CLI default output format: json
    Profile name: clucktalk
aws sso login --profile clucktalk
aws sts get-caller-identity --profile clucktalk
```

The profile stores no keys: `%USERPROFILE%\.aws\config` holds the session and role names; short-lived tokens are
cached under `%USERPROFILE%\.aws\sso\cache` [13]. Never commit either.

14. CLI install: https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html

Observed 2026-09-28: at the end of `aws configure sso`, CLI 2.37.4 also asked "Configure AWS skills and the AWS MCP
server for your AI coding agent(s)?"; we answered no (not needed for this project).

## 5. Verification (read-only first)

Run with `--profile clucktalk --region us-east-1`. Commands that could cost money or accept terms run only after the
account owner agrees. Results 2026-09-28 (CLI 2.37.4; account IDs never recorded):

| Check | Command | Result |
|---|---|---|
| Identity | `aws sts get-caller-identity` | assumed role `AWSReservedSSO_CluckTalkVerify_…` via Identity Center (no access keys) |
| Account plan | `aws freetier get-account-plan-state` | `accountPlanType: PAID`, `accountPlanStatus: ACTIVE` |
| Credits | `aws billing get-credits` | AccessDenied "IAM user access not activated" (account setting off; read credits in the console instead; FRICTION_LOG FL-015) |
| Seller of record | (no CLI command in 2.37.4) | AWS India, from the console Account page |
| Claude in us-east-1 | `aws bedrock list-foundation-models --by-provider anthropic` | all Claude models are `INFERENCE_PROFILE` only (no direct on-demand ID); e.g. Sonnet 5, Opus 5.5, Fable 5.1, Haiku 4.5 `ACTIVE` |
| Profiles | `aws bedrock list-inference-profiles --type-equals SYSTEM_DEFINED` | `us.` and `global.` profiles ACTIVE for `anthropic.claude-sonnet-5`, `anthropic.claude-haiku-4-5-20251001-v1:0`, `anthropic.claude-opus-5-5`, `anthropic.claude-fable-5-1`, `amazon.nova-2-lite-v1:0`; `us.` for `amazon.nova-lite-v1:0`, `amazon.nova-pro-v1:0` |
| Claude access | `aws bedrock get-foundation-model-availability` | Sonnet 5, Haiku 4.5: agreement `NOT_AVAILABLE` (no Marketplace agreement yet), authorization `AUTHORIZED`, entitlement and Region `AVAILABLE` |
| Nova access | same | Nova Lite, Nova 2 Lite: agreement `AVAILABLE`, `AUTHORIZED`, entitlement and Region `AVAILABLE` |
| Anthropic use-case form | `aws bedrock get-use-case-for-model-access` | not submitted yet |
| **Quotas** | `aws service-quotas list-service-quotas` vs `list-aws-default-service-quotas`, service `bedrock` | **0 in this account** for every requests/tokens-per-minute quota of Sonnet 5, Haiku 4.5, Nova Lite, Nova 2 Lite, Nova Pro (defaults are large, e.g. Sonnet 5 cross-Region TPM 6,000,000, L-D4FBCF4E). Live calls cannot work until raised (FRICTION_LOG FL-014) |
| Polly | `aws polly describe-voices --language-code en-IN` | Kajal (neural, generative), Aditi and Raveena (standard); `te-IN`: none |

### 5.1 Quota re-check after AWS Support reply (2026-09-29, FRICTION_LOG FL-016)

Support closed both quota cases 28–29 Sep: "Bedrock access has been enabled ... granted access to reduced quotas.
Some higher-tier foundation models may not be available." Re-ran the same read-only quota comparison (CLI 2.37.4,
`--profile clucktalk --region us-east-1`) rather than trusting the reply's wording:

| Model | Cross-region requests/min: applied (default) | Cross-region tokens/min: applied (default) | Marketplace agreement | Callable? |
|---|---|---|---|---|
| Amazon Nova 2 Lite | 20 (2,000) | 8,000,000 (8,000,000) | `AVAILABLE` | **Yes** — real nonzero quota + agreement in place. Not yet proven with a live call. |
| Anthropic Claude Haiku 4.5 | 10 (10,000) | 5,000,000 (5,000,000) | `NOT_AVAILABLE` | **No** — quota is now real (was 0), but the Marketplace agreement for Anthropic models still isn't created, which is the current blocker (same root cause as the 28 Sep `get-foundation-model-availability` row above). |
| Anthropic Claude Sonnet 5 | not found (no per-request quota listed) | 0 (6,000,000) | `NOT_AVAILABLE` | **No** — still 0 on the path CluckTalk would call (`us.`/`global.` inference profile); this is the "higher-tier" model the reply says may not be available. |

One more Sonnet 5 quota exists, `[bedrock-mantle endpoint] Input/Output tokens per minute for Claude Sonnet 5`,
applied = default (3,000,000 / 300,000, not reduced) — an unfamiliar quota name not documented anywhere seen so
far, and not the cross-region inference-profile path this project uses. Not relied on; flagged for one WebSearch
if Sonnet 5 access is still needed later.

**Read-only conclusion**: Nova 2 Lite is the only one of the three with both a real quota and an active Marketplace
agreement. Haiku 4.5's quota is fixed but it's still blocked by the missing Anthropic Marketplace agreement (needs
the account owner to accept it in the Bedrock console "Model access" page — a separate step from quota, costs
nothing). Sonnet 5 needs both the agreement and a further quota increase. No live Converse call made (Rule 4/6:
verify before claiming; a real call needs the account owner's go-ahead per the AWS checkpoint plan).

Unused permission found: `billing:GetSellerOfRecord` has no CLI command; drop it from the inline policy at the next
permission-set review.
