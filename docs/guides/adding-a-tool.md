# Adding a tool

A tool is a `Tool(spec, label, handler)`: a JSON-schema description for the model, a UI label, and an async handler that returns text.

## 1. Write the factory

Add it to `jarvis_core/application/tools/builtin.py`, or create a new module. It should depend on **ports**, never on concrete adapters:

```python
def stock_tools(quotes: QuoteProvider) -> list[Tool]:
    """``get_stock_price``."""

    async def get_stock_price(args: Mapping[str, Any]) -> str:
        symbol = text_arg(args, "symbol")          # raises ToolError if missing
        assert symbol is not None
        quote = await quotes.latest(symbol.upper())
        if quote is None:
            raise ToolError(f"no quote found for {symbol}")  # → "Error: …" for the model
        return f"{quote.symbol} is at {quote.price:.2f} {quote.currency}."

    return [
        Tool(
            ToolSpec(
                "get_stock_price",
                "Get the latest price of a stock by ticker symbol.",
                schema({"symbol": {"type": "string", "description": "Ticker, e.g. AAPL."}}, ["symbol"]),
            ),
            "Checking the markets",
            get_stock_price,
        )
    ]
```

Guidelines:

- **Descriptions are prompts.** Say *when* to use the tool, not just what it does.
- **Return short, factual sentences.** The model rephrases them as speech.
- **Raise `ToolError` for expected problems**, such as a missing argument, nothing found, or an ambiguous request. The registry turns it into an error message the model can explain.
- **Notify on change.** If the tool mutates data shown in a widget, call `notifier.data_changed("<topic>")`.

## 2. Add the port and adapter

Define `QuoteProvider` in `domain/ports.py`, implement it in `adapters/…`, and test the adapter with `httpx.MockTransport`.

## 3. Register it

In `container.assemble`:

```python
if quotes is not None:
    tools.extend(stock_tools(quotes))
```

Then build the adapter in `build_container`, behind a setting if it needs configuration.

## 4. Test it

Follow `tests/test_tools.py`: call `registry.execute(ToolCall("get_stock_price", {...}))` with a fake provider and assert on the returned text. To test the whole loop, script `FakeLlm(rounds=[[ToolCall(...)], ["final words"]])`.
