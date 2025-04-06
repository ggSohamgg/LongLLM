# AWS Lambda + RunPod Summarization Pipeline

This Lambda function automatically summarizes large transcription `.txt` files uploaded to an S3 bucket using a hosted model on RunPod.

---

## Recommended Model(s) and Justification

**Model:** [`Yarn LLaMA 2 13B 128K GPTQ`](https://huggingface.co/NousResearch/Yarn-Llama-2-13b-128k-GPTQ) (or) [`Nous-Yarn-Mistral-7B-128K`](https://huggingface.co/NousResearch/Yarn-Mistral-7b-64k)

### Why?
### ✅ Yarn-LLaMA-2-13B-128K-GPTQ  
🔗 [View on HuggingFace](https://huggingface.co/TheBloke/Yarn-LLaMA-2-13B-128K-GPTQ)  
- Best choice for **high-quality** summaries with detailed structure.  
- Works efficiently on a single 80GB GPU.  
- Balanced trade-off between performance and quality.

### ⚡ Nous-Yarn-Mistral-7B-128K  
🔗 [View on HuggingFace](https://huggingface.co/NousResearch/Yarn-Mistral-7b-64k)  
- Optimized for **speed and inference efficiency**.  
- Ideal for cost-sensitive deployments or faster turnaround.  
- Slightly lower output quality compared to the 13B variant.

### 🏅 Honorable Mention: Yarn-LLaMA-2-7B-128K-GPTQ  
🔗 [View on HuggingFace](https://huggingface.co/TheBloke/Yarn-Llama-2-7B-128K-GPTQ)  
- Lightweight alternative suitable for environments with **moderate GPU capacity**.  
- Still supports full 128K token context.  
- Good balance if fewer GPU resources are available.

> 💡 If more GPU resources are available, larger models like `LLaMA-2-70B` can potentially provide even better quality, but they require complex multi-GPU setups and significantly higher inference costs.

---

## How the Lambda Function Works

1. **Triggered** by an S3 event when a `.txt` file is uploaded.
2. Reads the transcription file from the S3 bucket.
3. Sends the text to the RunPod inference API for summarization.
4. Polls the job status until it's marked as `COMPLETED`.
5. Stores the summarized result back into S3 under a `summaries/` prefix.

---

## Environment Variables

The Lambda function expects the following environment variables:

| Variable Name        | Description                            |
|----------------------|----------------------------------------|
| `RUNPOD_API_KEY`     | Your RunPod API token                  |
| `RUNPOD_ENDPOINT_URL`| The endpoint URL of your RunPod model |
| `OUTPUT_BUCKET`      | (Optional) Destination S3 bucket       |
| `OUTPUT_PREFIX`      | (Optional) S3 prefix for summaries     |

---

##  Design Decisions

- **Polling Approach:**  
  Uses `poll_runpod_job()` to check job status every 5 seconds for up to 5 minutes. This is a simple and safe pattern for async completion on external APIs.

- **Error Handling:**  
  - Gracefully handles timeouts, network issues, and RunPod errors.
  - Fallback logic is built into output parsing to support flexible response formats.

- **Max Token Control:**  
  Limits response to ~16,000 tokens (approx. 4,000 words), which balances completeness with speed.

---

## Alternative: Pull-Based Approach

You can reverse the architecture:

1. Upload transcription to S3.
2. Generate a **pre-signed URL**.
3. Pass the URL to a **custom RunPod worker**.
4. Worker downloads the file and pushes the summary back via callback or S3.

### Pros:
- Fully decouples RunPod and Lambda.
- RunPod job can control retry logic, chunking, etc.

### Cons:
- Requires deploying and maintaining a custom RunPod worker container.
- Adds complexity in permission and security.

---

##  Testing Strategy (Before API Key)

You can test core logic **without needing a real API key**:

- **Mock RunPod API calls** using a library like `unittest.mock`.
- Simulate a dummy S3 event (sample JSON).
- Run `lambda_handler()` locally and assert:
  - S3 get call is triggered.
  - Summary is written correctly to `put_object`.

### 🔄 Or:
Temporarily replace `initiate_runpod_job()` and `poll_runpod_job()` with mocked functions that return a hardcoded summary.

---

##  Example S3 Key Flow

Input:  
`s3://my-transcripts/session1.txt`

Output:  
`s3://my-transcripts/summaries/session1_summary.txt`

---


