# Roxy GPT-SoVITS 本地 TTS 服务

这是一个给当前 Mac 本机部署的独立 TTS 服务层，使用：

- GPT-SoVITS 官方推理代码
- 洛琪希 `RoxyPro（新版）` 权重
- 本地参考音频默认声线
- HTTP 接口，后续可以直接接你们产品

## 目录

- 部署根目录：`/path/to/gpt-sovits-roxy`（通过 `ROXY_GSV_DEPLOY_ROOT` 环境变量指定）
- 服务脚本：`scripts/tts/roxy_gsv_service.py`
- 启动脚本：`scripts/tts/run_roxy_gsv_service.sh`
- 默认输出目录：`${ROXY_GSV_DEPLOY_ROOT}/outputs`

## 必需的环境变量

启动服务前必须设置以下环境变量：

| 变量 | 说明 | 示例 |
|------|------|------|
| `ROXY_GSV_DEPLOY_ROOT` | GPT-SoVITS 部署根目录 | `/Users/umikok7/Desktop/python/my-deer-flow/artifacts/gpt-sovits-roxy` |
| `ROXY_GSV_T2S_WEIGHTS` | GPT 权重路径 | `/path/to/YourChar.ckpt` |
| `ROXY_GSV_VITS_WEIGHTS` | VITS 权重路径 | `/path/to/YourChar.pth` |
| `ROXY_GSV_REF_AUDIO` | 默认参考音频路径 | `/path/to/reference.wav` |

可选变量：

| 变量 | 默认值 | 说明 |
|------|------|------|
| `ROXY_GSV_PROMPT_LANG` | `ja` | 参考音频语种 |
| `ROXY_GSV_TEXT_LANG` | `zh` | 输出语种 |
| `ROXY_GSV_HOST` | `127.0.0.1` | 监听地址 |
| `ROXY_GSV_PORT` | `9881` | 监听端口 |

## 启动

```bash
# 设置环境变量后启动
export ROXY_GSV_DEPLOY_ROOT=/path/to/gpt-sovits-roxy
export ROXY_GSV_T2S_WEIGHTS=/path/to/YourChar.ckpt
export ROXY_GSV_VITS_WEIGHTS=/path/to/YourChar.pth
export ROXY_GSV_REF_AUDIO=/path/to/reference.wav

scripts/tts/run_roxy_gsv_service.sh
```

默认监听：

```text
http://127.0.0.1:9881
```

## 健康检查

```bash
curl http://127.0.0.1:9881/health
```

## 直接返回音频

```bash
curl -X POST http://127.0.0.1:9881/tts \
  -H 'Content-Type: application/json' \
  -o /tmp/roxy-test.wav \
  -d '{
    "text": "本次任务已经顺利完成，交付结果已整理完毕，请您查收。",
    "text_lang": "zh"
  }'
```

## 保存到文件并返回路径

```bash
curl -X POST http://127.0.0.1:9881/tts/file \
  -H 'Content-Type: application/json' \
  -d '{
    "text": "本次任务已经顺利完成，交付结果已整理完毕，请您查收。",
    "text_lang": "zh"
  }'
```

## 常用可选参数

请求体支持这些字段：

- `text`
- `text_lang`
- `ref_audio_path`
- `prompt_text`
- `prompt_lang`
- `speed_factor`
- `top_k`
- `top_p`
- `temperature`

如果不传 `prompt_text`，服务会自动用参考音频文件名作为默认 prompt 文本。

## 换用自己的角色声线

只需设置不同的权重路径和环境变量即可：

```bash
export ROXY_GSV_T2S_WEIGHTS=/path/to/YourCharacter.ckpt
export ROXY_GSV_VITS_WEIGHTS=/path/to/YourCharacter.pth
export ROXY_GSV_REF_AUDIO=/path/to/your-reference.wav
scripts/tts/run_roxy_gsv_service.sh
```