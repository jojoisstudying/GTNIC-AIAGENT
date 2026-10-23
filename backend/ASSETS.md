# Human photo and pose asset workflow

## Architecture

- Reference photos and generated images are stored only under `data/` (ignored by Git).
- `data/app.db` stores tags, person ID, model/prompt provenance, cache key, and review status.
- Image variants are cached by person ID + reference-photo content hash + pose/prompt + model. Rendering reuses that cache rather than calling the image API again.
- Generated files are automatically cut out locally with `rembg`/U2Net, saved as transparent PNG, and begin as `pending_review`. The Designer never renders an unapproved AI image. After visual inspection and approval, the next render reuses it.
- First use may download the U2Net model weights to the user's local cache; no second image-generation API call is made for the cutout step.
- With Cloudflare configured, `scripts.run_all` generates missing pose assets and renders the carousel. It pauses before publishing while generated images are pending human review.

## Cloudflare account values to create

In Cloudflare Dashboard → Workers AI → Use REST API, create a **Workers AI API Token** and copy the **Account ID**. The documented token template has Workers AI Read/Edit permissions. Do not paste these secrets in chat or commit them to Git.

Add these entries to the local `step1/.env` (the values below are placeholders, not real secrets):

```dotenv
CLOUDFLARE_ACCOUNT_ID=your_account_id
CLOUDFLARE_API_TOKEN=your_workers_ai_token
CLOUDFLARE_IMAGE_MODEL=@cf/black-forest-labs/flux-2-klein-9b
CLOUDFLARE_POSE_PERSON_ID=operator_01
CLOUDFLARE_POSE_GENERATION=false
```

Workers AI currently documents 10,000 Neurons/day free allocation; it is a quota, not unlimited free use. Above the allowance requires Workers Paid and usage charges. Check current model pricing/eligibility in the Cloudflare dashboard before generating. FLUX.2 Klein 9B supports reference-image editing, but it does not guarantee identity, uniform, logo, or PPE fidelity.

## Register a real reference photo

Use a photo you have permission to process, preferably clear, well-lit, full-body, wearing the correct work clothes/PPE. Register it from the `step1` directory:

```text
python -m scripts.add_person operator_01 /path/to/approved_photo.jpg --consent-confirmed
```

This copies the photo to `data/people/operator_01/reference.jpg`. The consent flag confirms permission for AI editing and sending the image to Cloudflare Workers AI. Do not use a person's photo without that permission.

## Generate once, review, reuse

The normal one-command run generates every distinct pose tag used by the current carousel from the registered reference photo, removes each image background locally, runs image QC, stages transparent PNGs for review, and renders the carousel. It then pauses for approval. Repeated poses reuse the same image; each uncached pose can make one Cloudflare request:

```text
python -m scripts.run_all "tips keselamatan kerja di area produksi"
python -m scripts.list_assets
```

The automated QC checks file integrity, minimum resolution, alpha transparency and a basic portrait shape. Still inspect the transparent PNG visually, especially cutout edges, face, hands, uniform, company marks, and PPE. Approve each suitable pending asset ID:

```text
python -m scripts.approve_asset 123 --approve
python -m scripts.run_designer
python -m scripts.publish_approved
```

Reject unsuitable images with `python -m scripts.approve_asset 123 --reject`. To request a fresh variation intentionally, use `python -m scripts.generate_pose operator_01 senyum --force`; this can consume additional quota.

Generation is enabled by default for `scripts.run_all`; pass `--no-generate` to use only currently approved assets. A person ID must be set in `CLOUDFLARE_POSE_PERSON_ID` or in `config/brand.json` under `pose_generation.person_id`. The publish command still requires typing `POST`, and refuses to run when there are pending images, failed QC, or non-transparent photos.

## Operational notes

- Existing database rows migrate automatically and are treated as approved, preserving current manual assets and placeholders.
- A matching cached cutout is returned without another image-generation request. Older opaque cached images are locally cut out and staged for review without calling Cloudflare again. Rejected variants remain cached; `--force` intentionally creates another variant.
- The app only passes the reference image to Workers AI when you explicitly invoke generation or enable auto-staging. Reference and output images remain local; API credentials are read from environment variables.
- Generated assets are never published automatically merely because they were approved; the regular Publisher consent and preflight gates still apply.
