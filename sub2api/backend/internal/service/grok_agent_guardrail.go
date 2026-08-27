package service

import (
	"bytes"
	"encoding/json"
	"fmt"
	"strings"
)

const grokAgentActionPolicyMarker = "[GROKAPI_ACTION_GROUNDING]"

const grokAgentActionPolicy = grokAgentActionPolicyMarker + `
The latest user message asks you to perform an action, not merely explain commands.
- Use an appropriate provided tool before reporting that the action was performed.
- Never claim that you started, stopped, changed, deleted, restored, deployed, or verified anything unless a successful tool result in this turn proves it.
- After a state-changing tool call, use a read-only check when available and report the observed result or exact error.
- If no appropriate tool is available or permission is denied, explicitly say the action was not performed. Do not invent a port, path, process, file, or database state.`

const grokAgentDestructivePolicy = `
- This request may be destructive. Inspect and identify the exact target first. Do not delete, clear, reset, overwrite, or restore a guessed target.`

// applyGrokAgentActionGuardrail grounds agent-style action requests in actual
// tool results. It leaves ordinary chat untouched, so greetings and questions
// do not pay an extra prompt or tool-call cost.
func applyGrokAgentActionGuardrail(body []byte) ([]byte, error) {
	var request map[string]any
	decoder := json.NewDecoder(bytes.NewReader(body))
	decoder.UseNumber()
	if err := decoder.Decode(&request); err != nil {
		return nil, fmt.Errorf("decode Grok action guardrail request: %w", err)
	}

	tools, _ := request["tools"].([]any)
	if len(tools) == 0 {
		return body, nil
	}

	userText, toolResultAfterUser := latestGrokUserTextAndToolResult(request["input"])
	if !isGrokAgentActionRequest(userText) {
		return body, nil
	}

	instructions, _ := request["instructions"].(string)
	if !strings.Contains(instructions, grokAgentActionPolicyMarker) {
		policy := grokAgentActionPolicy
		if isGrokDestructiveActionRequest(userText) {
			policy += grokAgentDestructivePolicy
		}
		if strings.TrimSpace(instructions) == "" {
			request["instructions"] = policy
		} else {
			request["instructions"] = strings.TrimRight(instructions, " \t\r\n") + "\n\n" + policy
		}
	}

	// Force the first action step only. Once a tool result follows the latest
	// user message, restore auto selection so the model can finish normally.
	if !toolResultAfterUser && hasGrokActionCapableTool(tools) {
		choice, exists := request["tool_choice"]
		if !exists || strings.EqualFold(strings.TrimSpace(fmt.Sprint(choice)), "auto") {
			request["tool_choice"] = "required"
		}
	}

	out, err := marshalOpenAIUpstreamJSON(request)
	if err != nil {
		return nil, fmt.Errorf("encode Grok action guardrail request: %w", err)
	}
	return out, nil
}

func latestGrokUserTextAndToolResult(input any) (string, bool) {
	if text, ok := input.(string); ok {
		return strings.TrimSpace(text), false
	}
	items, ok := input.([]any)
	if !ok {
		return "", false
	}

	latestUser := -1
	latestText := ""
	for i, raw := range items {
		item, ok := raw.(map[string]any)
		if !ok || !strings.EqualFold(grokGuardrailStringValue(item["role"]), "user") {
			continue
		}
		latestUser = i
		latestText = grokMessageText(item["content"])
	}
	if latestUser < 0 {
		return "", false
	}

	for _, raw := range items[latestUser+1:] {
		item, ok := raw.(map[string]any)
		if !ok {
			continue
		}
		typeName := strings.ToLower(grokGuardrailStringValue(item["type"]))
		role := strings.ToLower(grokGuardrailStringValue(item["role"]))
		if role == "tool" || strings.HasSuffix(typeName, "_call_output") || typeName == "function_call_output" {
			return strings.TrimSpace(latestText), true
		}
	}
	return strings.TrimSpace(latestText), false
}

func grokMessageText(content any) string {
	if text, ok := content.(string); ok {
		return text
	}
	parts, ok := content.([]any)
	if !ok {
		return ""
	}
	var texts []string
	for _, raw := range parts {
		part, ok := raw.(map[string]any)
		if !ok {
			continue
		}
		if text := grokGuardrailStringValue(part["text"]); text != "" {
			texts = append(texts, text)
		}
	}
	return strings.Join(texts, "\n")
}

func grokGuardrailStringValue(value any) string {
	text, _ := value.(string)
	return strings.TrimSpace(text)
}

func isGrokAgentActionRequest(text string) bool {
	text = strings.ToLower(strings.TrimSpace(text))
	if text == "" {
		return false
	}
	// "làm sao/cách ..." asks for instructions, not execution.
	for _, questionPrefix := range []string{"làm sao", "lam sao", "cách ", "cach ", "how do ", "how can ", "how to "} {
		if strings.HasPrefix(text, questionPrefix) {
			return false
		}
	}
	for _, phrase := range []string{
		"khởi chạy", "khoi chay", "tự chạy", "tu chay", "chạy lên", "chay len", "chạy đi", "chay di",
		"mở lên", "mo len", "sửa đi", "sua di", "fix đi", "fix di", "làm hết", "lam het", "đẩy đi", "day di",
		"xóa ", "xoá ", "xoa ", "clear ", "khôi phục", "khoi phuc", "cài ", "cai ", "gia hạn", "gia han",
		"push ", "deploy ", "restart", "start ", "stop ", "run ", "fix ", "delete ", "remove ", "restore ",
		"install ", "create ", "update ", "edit ", "change ", "open ", "launch ", "execute ",
	} {
		if strings.Contains(text, phrase) {
			return true
		}
	}
	return false
}

func isGrokDestructiveActionRequest(text string) bool {
	text = strings.ToLower(text)
	for _, phrase := range []string{
		"xóa", "xoá", "xoa ", "clear ", "delete ", "remove ", "drop ", "reset ", "overwrite ", "format ",
	} {
		if strings.Contains(text, phrase) {
			return true
		}
	}
	return false
}

func hasGrokActionCapableTool(tools []any) bool {
	for _, raw := range tools {
		tool, ok := raw.(map[string]any)
		if !ok {
			continue
		}
		name := strings.ToLower(grokGuardrailStringValue(tool["name"]))
		typeName := strings.ToLower(grokGuardrailStringValue(tool["type"]))
		if typeName == "computer_use_preview" || typeName == "computer" {
			return true
		}
		for _, token := range []string{"bash", "shell", "exec", "terminal", "computer", "apply_patch", "write", "edit", "browser", "navigate", "click"} {
			if strings.Contains(name, token) {
				return true
			}
		}
	}
	return false
}
