# 🚀 Groq Setup - FREE & Fast Transcription!

## Why Groq?

- ✅ **100% FREE** (generous free tier)
- ✅ **5x FASTER** than OpenAI Whisper
- ✅ **Better accuracy** in many cases
- ✅ **14,400 requests/day** free tier
- ✅ No credit card required for free tier

## 🔑 Get Your Free Groq API Key

### Step 1: Sign Up (Free)

1. Go to: **https://console.groq.com/**
2. Click **"Sign Up"**
3. Create account (email or GitHub/Google)
4. **No credit card required!**

### Step 2: Get API Key

1. Once logged in, go to: **https://console.groq.com/keys**
2. Click **"Create API Key"**
3. Copy your key (starts with `gsk_...`)

## 📝 Configure drTranscribe for Groq

### Option 1: Update config/settings.yaml

```yaml
transcription:
  provider: "groq"
  model: "whisper-large-v3"

extraction:
  provider: "azure"
  model: "gpt-4.1-mini"
  temperature: 0.3

# Groq Configuration (FREE!)
groq:
  api_key: "${GROQ_API_KEY}"

# Azure OpenAI Configuration
azure_openai:
  api_key: "${AZURE_OPENAI_API_KEY}"
  endpoint: "https://llmproxyhub5196723659.cognitiveservices.azure.com/"
  api_version: "2024-04-01-preview"
  whisper_deployment: "whisper"
  gpt_deployment: "gpt-4.1-mini"

server:
  host: "0.0.0.0"
  port: 8000
```

### Option 2: Set Environment Variable

```bash
export GROQ_API_KEY=gsk_your_groq_api_key_here
```

## 🚀 Install & Start

```bash
# Install groq package
pip install groq

# Set API keys
export GROQ_API_KEY=gsk_your_groq_key_here
export AZURE_OPENAI_API_KEY=your_azure_key_here

# Restart server
./start.sh
```

## ✅ Expected Output

```
🚀 Initialized Groq Whisper provider with model: whisper-large-v3 (FREE!)
INFO - Initialized Azure GPT provider with deployment: gpt-4.1-mini
INFO:     Uvicorn running on http://0.0.0.0:8000
```

## 🎯 Test It!

1. Open `http://localhost:8000`
2. Fill patient info
3. Click "Start Recording"
4. **Speak into your microphone**
5. Watch REAL transcription appear!

## 📊 Groq Models Available

Choose one in `config/settings.yaml`:

```yaml
transcription:
  model: "whisper-large-v3"        # Best quality (recommended)
  # model: "whisper-large-v3-turbo" # Faster, slightly lower quality
```

## 💰 Cost Comparison

| Provider | Cost (1000 consultations/month) |
|----------|--------------------------------|
| OpenAI Whisper | $60/month |
| Azure Whisper | ~$40/month |
| **Groq Whisper** | **$0 (FREE!)** |

## 🎉 Benefits

- **No quota errors** (generous limits)
- **Lightning fast** (5x faster responses)
- **High quality** (same Whisper models)
- **Perfect for MVP** (validate idea for free)

## 🔄 Switch Providers Easily

### Use Groq for Transcription + Azure for Extraction

```yaml
transcription:
  provider: "groq"          # FREE!

extraction:
  provider: "azure"         # Your existing Azure GPT
```

### Use Groq for Both (If you want)

Groq also has Llama models for extraction (even cheaper):

```yaml
transcription:
  provider: "groq"

extraction:
  provider: "groq"
  model: "llama-3.1-70b"
```

## 🐛 Troubleshooting

### "Module 'groq' not found"

```bash
pip install groq
```

### "Invalid API key"

- Check your key starts with `gsk_`
- Verify at: https://console.groq.com/keys
- Make sure it's set: `echo $GROQ_API_KEY`

### "Rate limit exceeded"

Free tier limits:
- 14,400 requests/day
- 30 requests/minute

If you hit limits, you're probably testing a LOT! 😄

## 🌟 Recommended Setup (Best of Both Worlds)

```yaml
transcription:
  provider: "groq"          # FREE & Fast
  model: "whisper-large-v3"

extraction:
  provider: "azure"         # Your existing Azure
  model: "gpt-4.1-mini"
```

This gives you:
- ✅ FREE transcription (Groq)
- ✅ Quality extraction (Azure GPT)
- ✅ No OpenAI quota issues
- ✅ Fast responses

---

**Get your free Groq key and test now!** 🚀

https://console.groq.com/keys
