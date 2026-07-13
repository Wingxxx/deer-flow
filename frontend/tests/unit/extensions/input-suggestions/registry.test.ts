import { describe, test, expect, beforeEach } from "@rstest/core";

import {
  registerInputSuggestion,
  getInputSuggestions,
  clearInputSuggestions,
} from "../../../../extensions/input-suggestions/registry";

describe("InputSuggestions Registry", () => {
  beforeEach(() => {
    clearInputSuggestions();
  });

  test("should register and retrieve a suggestion", () => {
    registerInputSuggestion({
      id: "test",
      label: "Test",
      prompt: "Test [x]",
      icon: null as any,
      group: "main",
    });
    const all = getInputSuggestions();
    expect(all).toHaveLength(1);
    expect(all[0]!.id).toBe("test");
    expect(all[0]!.group).toBe("main");
  });

  test("should ignore duplicate id", () => {
    registerInputSuggestion({
      id: "test",
      label: "A",
      prompt: "A [x]",
      icon: null as any,
      group: "main",
    });
    registerInputSuggestion({
      id: "test",
      label: "B",
      prompt: "B [x]",
      icon: null as any,
      group: "main",
    });
    expect(getInputSuggestions()).toHaveLength(1);
    expect(getInputSuggestions()[0]!.label).toBe("A");
  });

  test("should filter by group", () => {
    registerInputSuggestion({
      id: "a",
      label: "A",
      prompt: "A [x]",
      icon: null as any,
      group: "main",
    });
    registerInputSuggestion({
      id: "b",
      label: "B",
      prompt: "B [x]",
      icon: null as any,
      group: "create",
    });
    const all = getInputSuggestions();
    expect(all.filter((s) => s.group === "main")).toHaveLength(1);
    expect(all.filter((s) => s.group === "create")).toHaveLength(1);
  });

  test("should return empty after clear", () => {
    registerInputSuggestion({
      id: "test",
      label: "A",
      prompt: "A [x]",
      icon: null as any,
      group: "main",
    });
    clearInputSuggestions();
    expect(getInputSuggestions()).toHaveLength(0);
  });

  test("should return empty when nothing registered", () => {
    expect(getInputSuggestions()).toHaveLength(0);
  });
});
