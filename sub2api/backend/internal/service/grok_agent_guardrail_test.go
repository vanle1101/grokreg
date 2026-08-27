//go:build unit

package service

import (
	"encoding/json"
	"testing"

	"github.com/stretchr/testify/require"
	"github.com/tidwall/gjson"
)

func TestGrokAgentActionGuardrailForcesFirstToolStep(t *testing.T) {
	t.Parallel()
	body := []byte(`{
		"model":"grok-4.6",
		"input":[{"role":"user","content":[{"type":"input_text","text":"tự chạy dashboard lên cho t"}]}],
		"instructions":"Follow project rules.",
		"tools":[{"type":"function","name":"Bash","parameters":{"type":"object"}}],
		"tool_choice":"auto"
	}`)

	patched, err := applyGrokAgentActionGuardrail(body)
	require.NoError(t, err)
	require.Equal(t, "required", gjson.GetBytes(patched, "tool_choice").String())
	require.Contains(t, gjson.GetBytes(patched, "instructions").String(), "Follow project rules.")
	require.Contains(t, gjson.GetBytes(patched, "instructions").String(), grokAgentActionPolicyMarker)
}

func TestPatchGrokResponsesBodyAppliesActionGuardrailAfterClientToolAdaptation(t *testing.T) {
	t.Parallel()
	body := []byte(`{
		"model":"grok-4.6",
		"input":[{"role":"user","content":"fix đi"}],
		"tools":[{"type":"custom","name":"apply_patch","description":"edit files"}],
		"tool_choice":"auto"
	}`)

	patched, mapping, err := patchGrokResponsesBodyWithClientTools(body, "grok-4.6")
	require.NoError(t, err)
	require.True(t, mapping.CustomTools["apply_patch"])
	require.Equal(t, "function", gjson.GetBytes(patched, "tools.0.type").String())
	require.Equal(t, "required", gjson.GetBytes(patched, "tool_choice").String())
	require.Contains(t, gjson.GetBytes(patched, "instructions").String(), grokAgentActionPolicyMarker)
}

func TestGrokAgentActionGuardrailLeavesOrdinaryChatUntouched(t *testing.T) {
	t.Parallel()
	for _, input := range []string{"hi", "làm sao để khởi chạy dashboard?", "API này do đâu mà chậm?"} {
		body := []byte(`{"input":` + mustJSONQuote(input) + `,"tools":[{"type":"function","name":"Bash"}],"tool_choice":"auto"}`)
		patched, err := applyGrokAgentActionGuardrail(body)
		require.NoError(t, err)
		require.JSONEq(t, string(body), string(patched))
	}
}

func TestGrokAgentActionGuardrailDoesNotForceAnotherToolAfterResult(t *testing.T) {
	t.Parallel()
	body := []byte(`{
		"input":[
			{"role":"user","content":"khởi chạy dashboard lên"},
			{"type":"function_call","name":"Bash","call_id":"call_1","arguments":"{}"},
			{"type":"function_call_output","call_id":"call_1","output":"server listening"}
		],
		"tools":[{"type":"function","name":"Bash"}],
		"tool_choice":"auto"
	}`)

	patched, err := applyGrokAgentActionGuardrail(body)
	require.NoError(t, err)
	require.Equal(t, "auto", gjson.GetBytes(patched, "tool_choice").String())
	require.Contains(t, gjson.GetBytes(patched, "instructions").String(), grokAgentActionPolicyMarker)
}

func TestGrokAgentActionGuardrailAddsDestructiveInspectionRule(t *testing.T) {
	t.Parallel()
	body := []byte(`{"input":"clear hết database đi","tools":[{"type":"function","name":"Bash"}],"tool_choice":"auto"}`)
	patched, err := applyGrokAgentActionGuardrail(body)
	require.NoError(t, err)
	require.Equal(t, "required", gjson.GetBytes(patched, "tool_choice").String())
	require.Contains(t, gjson.GetBytes(patched, "instructions").String(), "Inspect and identify the exact target first")
}

func TestGrokAgentActionGuardrailDoesNotForceSearchOnlyTool(t *testing.T) {
	t.Parallel()
	body := []byte(`{"input":"khởi chạy dashboard lên","tools":[{"type":"function","name":"web_search"}],"tool_choice":"auto"}`)
	patched, err := applyGrokAgentActionGuardrail(body)
	require.NoError(t, err)
	require.Equal(t, "auto", gjson.GetBytes(patched, "tool_choice").String())
	require.Contains(t, gjson.GetBytes(patched, "instructions").String(), grokAgentActionPolicyMarker)
}

func mustJSONQuote(value string) string {
	quoted, _ := json.Marshal(value)
	return string(quoted)
}
