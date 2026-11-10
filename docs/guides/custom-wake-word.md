# Custom wake word: "Hello Jarvis"

openWakeWord ships a pretrained **`hey_jarvis`** model, which is the default. It sometimes fires for "Hello Jarvis" too, but not reliably. For the exact phrase, train your own model. Training is free and needs no recordings of your voice, because the model is trained on synthetic speech.

## Train (about an hour, free GPU on Google Colab)

1. Open the openWakeWord repository: <https://github.com/dscripka/openWakeWord>.
2. Follow the **"Training New Models"** section of its README, which links a Google Colab notebook for automatic model training.
3. Set the target phrase to `hello jarvis`. Optionally add phrases it should *not* react to, such as "hello", "jarvis" and "hey travis".
4. Run all cells and download the resulting **`hello_jarvis.onnx`**.

## Use it

```bash
mkdir services/core/models
# copy hello_jarvis.onnx into services/core/models/
```

In `services/core/.env`:

```dotenv
JARVIS_WAKE_MODEL=models/hello_jarvis.onnx
JARVIS_WAKE_THRESHOLD=0.5
```

Restart `pnpm dev:core`. The engage screen hint and the Systems widget will now say **"Hello Jarvis"**. The UI derives the phrase from the model's file name.

## Tuning

| Problem                         | Adjust                                        |
| ------------------------------- | --------------------------------------------- |
| Misses you from across the room | `JARVIS_WAKE_THRESHOLD=0.35`, or use a better mic |
| Triggers on TV dialogue         | `JARVIS_WAKE_THRESHOLD=0.7`; retrain with more negative phrases |

!!! tip
    `*.onnx` files are git-ignored. Keep your trained model backed up somewhere else.
