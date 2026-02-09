# Azure OpenAI Setup Guide

## ✅ Configuration Complete!

Your drTranscribe MVP is now configured to use Azure OpenAI instead of regular OpenAI.

## 🔑 Set Your Azure API Key

### Option 1: Environment Variable (Quick)

```bash
export AZURE_OPENAI_API_KEY=your_azure_api_key_here
```

### Option 2: .env File (Persistent)

Create a `.env` file:

```bash
echo "AZURE_OPENAI_API_KEY=your_azure_api_key_here" > .env
```

## 📝 Current Configuration

Your `config/settings.yaml` is now set to:

```yaml
transcription:
  provider: "azure"
  model: "whisper"

extraction:
  provider: "azure"
  model: "gpt-4.1-mini"

azure_openai:
  api_key: "${AZURE_OPENAI_API_KEY}"
  endpoint: "https://llmproxyhub5196723659.cognitiveservices.azure.com/"
  api_version: "2024-08-01-preview"
  whisper_deployment: "whisper"
  gpt_deployment: "gpt-4.1-mini"
```

## 🚀 Start the Server

```bash
# Stop the current server (Ctrl+C if running)

# Set your Azure API key
export AZURE_OPENAI_API_KEY=your_actual_azure_key

# Start the server
./start.sh
```

## ⚠️ Important Notes

### Whisper Deployment

If your Azure OpenAI doesn't have a "whisper" deployment, you have two options:

**Option 1: Create a Whisper deployment in Azure**
1. Go to Azure OpenAI Studio
2. Navigate to Deployments
3. Create new deployment
4. Select model: whisper
5. Name it: "whisper"

**Option 2: Use a different deployment name**

If you have a whisper deployment with a different name, update `config/settings.yaml`:

```yaml
azure_openai:
  whisper_deployment: "your-whisper-deployment-name"
```

### If You Don't Have Whisper on Azure

If your Azure account doesn't have Whisper available, you can:

1. **Mix providers** - Use Azure for extraction only, and OpenAI for transcription:

```yaml
transcription:
  provider: "openai"
  model: "whisper-1"

extraction:
  provider: "azure"
  model: "gpt-4.1-mini"

openai:
  api_key: "${OPENAI_API_KEY}"

azure_openai:
  api_key: "${AZURE_OPENAI_API_KEY}"
  endpoint: "https://llmproxyhub5196723659.cognitiveservices.azure.com/"
  api_version: "2024-08-01-preview"
  gpt_deployment: "gpt-4.1-mini"
```

Then set both API keys:
```bash
export OPENAI_API_KEY=sk-your-openai-key
export AZURE_OPENAI_API_KEY=your-azure-key
```

## ✅ Testing

After starting the server:

1. Open browser: `http://localhost:8000`
2. Fill in patient info
3. Click "Start Recording"
4. Speak a test consultation
5. Watch the extractions appear!

## 🐛 Troubleshooting

### "Deployment not found" error

If you get a deployment error, check:
- Your deployment names in Azure OpenAI Studio
- Update `gpt_deployment` and `whisper_deployment` in config/settings.yaml

### "Invalid API key" error

- Verify your Azure API key is correct
- Check it's set in environment: `echo $AZURE_OPENAI_API_KEY`
- Make sure there are no extra spaces

### "Endpoint not found" error

- Verify the endpoint URL is correct
- Should end with .cognitiveservices.azure.com/
- Include the trailing slash

## 📊 Cost Comparison

Azure OpenAI is generally **cheaper** than direct OpenAI API:
- Better rate limits
- Often part of enterprise agreements
- More control over deployments

## 🎉 Benefits of Azure OpenAI

- ✅ Better quota management
- ✅ Enterprise-grade security
- ✅ Private networking options
- ✅ Integration with Azure services
- ✅ Often part of existing Azure subscriptions

## 🔄 Switching Back to OpenAI

If you ever want to switch back to regular OpenAI, just change provider in `config/settings.yaml`:

```yaml
transcription:
  provider: "openai"

extraction:
  provider: "openai"
```

And set `OPENAI_API_KEY` instead.

---

**Ready to test with Azure OpenAI!** 🚀
