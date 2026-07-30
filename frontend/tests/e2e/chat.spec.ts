import { expect, test } from "@playwright/test";

import { handleRunStream, mockLangGraphAPI } from "./utils/mock-api";

test.describe("Chat workspace", () => {
  test.beforeEach(async ({ page }) => {
    mockLangGraphAPI(page);
  });

  test("new chat page loads with input box", async ({ page }) => {
    await page.goto("/workspace/chats/new");

    const textarea = page.getByPlaceholder(/how can i assist you/i);
    await expect(textarea).toBeVisible({ timeout: 15_000 });
    await expect(page.getByRole("button", { name: /load more/i })).toBeHidden();
  });

  test("can type a message in the input box", async ({ page }) => {
    await page.goto("/workspace/chats/new");

    const textarea = page.getByPlaceholder(/how can i assist you/i);
    await expect(textarea).toBeVisible({ timeout: 15_000 });

    await textarea.fill("Hello, DeerFlow!");
    await expect(textarea).toHaveValue("Hello, DeerFlow!");
  });

  test("suggests matching skills after a leading slash", async ({ page }) => {
    await page.goto("/workspace/chats/new");

    const textarea = page.getByPlaceholder(/how can i assist you/i);
    await expect(textarea).toBeVisible({ timeout: 15_000 });

    await textarea.fill("/dat");
    await expect(
      page.getByRole("option", { name: /data-analysis/i }),
    ).toBeVisible();
    await expect(
      page.getByRole("option", { name: /disabled-skill/i }),
    ).toBeHidden();

    await textarea.press("Enter");

    await expect(textarea).toHaveValue("/data-analysis ");
  });

  test("keeps Shift+Enter as newline while skill suggestions are visible", async ({
    page,
  }) => {
    await page.goto("/workspace/chats/new");

    const textarea = page.getByPlaceholder(/how can i assist you/i);
    await expect(textarea).toBeVisible({ timeout: 15_000 });

    await textarea.fill("/dat");
    await expect(
      page.getByRole("option", { name: /data-analysis/i }),
    ).toBeVisible();

    await textarea.press("Shift+Enter");

    await expect(textarea).toHaveValue("/dat\n");
    await expect(
      page.getByRole("option", { name: /data-analysis/i }),
    ).toBeHidden();
  });

  test("does not suggest skills for slash text away from the prompt start", async ({
    page,
  }) => {
    await page.goto("/workspace/chats/new");

    const textarea = page.getByPlaceholder(/how can i assist you/i);
    await expect(textarea).toBeVisible({ timeout: 15_000 });

    await textarea.fill("please /dat");

    await expect(
      page.getByRole("option", { name: /data-analysis/i }),
    ).toBeHidden();
  });

  test("sending a message triggers API call and shows response", async ({
    page,
  }) => {
    let streamCalled = false;
    await page.route("**/runs/stream", (route) => {
      streamCalled = true;
      return handleRunStream(route);
    });

    await page.goto("/workspace/chats/new");

    const textarea = page.getByPlaceholder(/how can i assist you/i);
    await expect(textarea).toBeVisible({ timeout: 15_000 });

    await textarea.fill("Hello");
    await textarea.press("Enter");

    await expect.poll(() => streamCalled, { timeout: 10_000 }).toBeTruthy();

    // The AI response should appear in the chat
    await expect(page.getByText("Hello from DeerFlow!")).toBeVisible({
      timeout: 10_000,
    });
  });

  test("slash skill command is submitted as normal chat text", async ({
    page,
  }) => {
    const slashCommand = "/data-analysis analyze uploads/foo.csv";
    let submittedText: string | undefined;
    await page.route("**/runs/stream", (route) => {
      const body = route.request().postDataJSON() as {
        input?: { messages?: Array<{ content?: unknown }> };
      };
      const content = body.input?.messages?.at(-1)?.content;
      if (typeof content === "string") {
        submittedText = content;
      } else if (Array.isArray(content)) {
        submittedText = content
          .map((block) =>
            typeof block === "object" &&
            block !== null &&
            "text" in block &&
            typeof block.text === "string"
              ? block.text
              : "",
          )
          .join("");
      }
      return handleRunStream(route);
    });

    await page.goto("/workspace/chats/new");

    const textarea = page.getByPlaceholder(/how can i assist you/i);
    await expect(textarea).toBeVisible({ timeout: 15_000 });

    await textarea.fill(slashCommand);
    await textarea.press("Enter");

    await expect
      .poll(() => submittedText, { timeout: 10_000 })
      .toBe(slashCommand);
    await expect(page.getByText("Hello from DeerFlow!")).toBeVisible({
      timeout: 10_000,
    });
  });

  test("slash skill command with attachment preserves command text and file metadata", async ({
    page,
  }) => {
    const slashCommand = "/data-analysis analyze report.docx";
    let uploadCalled = false;
    let submittedText: string | undefined;
    let submittedFiles:
      | Array<{ filename?: string; path?: string; status?: string }>
      | undefined;

    await page.route("**/api/threads/*/uploads", async (route) => {
      uploadCalled = true;
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          success: true,
          message: "Uploaded",
          files: [
            {
              filename: "report.docx",
              size: 12,
              path: "report.docx",
              virtual_path: "/mnt/user-data/uploads/report.docx",
              artifact_url: "/api/threads/test/uploads/report.docx",
              extension: ".docx",
            },
          ],
        }),
      });
    });

    await page.route("**/runs/stream", (route) => {
      const body = route.request().postDataJSON() as {
        input?: {
          messages?: Array<{
            content?: unknown;
            additional_kwargs?: {
              files?: Array<{
                filename?: string;
                path?: string;
                status?: string;
              }>;
            };
          }>;
        };
      };
      const message = body.input?.messages?.at(-1);
      const content = message?.content;
      if (typeof content === "string") {
        submittedText = content;
      } else if (Array.isArray(content)) {
        submittedText = content
          .map((block) =>
            typeof block === "object" &&
            block !== null &&
            "text" in block &&
            typeof block.text === "string"
              ? block.text
              : "",
          )
          .join("");
      }
      submittedFiles = message?.additional_kwargs?.files;
      return handleRunStream(route);
    });

    await page.goto("/workspace/chats/new");

    const textarea = page.getByPlaceholder(/how can i assist you/i);
    await expect(textarea).toBeVisible({ timeout: 15_000 });

    await page.getByLabel("Upload files").setInputFiles({
      name: "report.docx",
      mimeType:
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
      buffer: Buffer.from("fake docx"),
    });

    await textarea.fill(slashCommand);
    await textarea.press("Enter");

    await expect.poll(() => uploadCalled, { timeout: 10_000 }).toBeTruthy();
    await expect
      .poll(() => submittedText, { timeout: 10_000 })
      .toBe(slashCommand);
    await expect
      .poll(() => submittedFiles, { timeout: 10_000 })
      .toEqual([
        {
          filename: "report.docx",
          size: 12,
          path: "/mnt/user-data/uploads/report.docx",
          status: "uploaded",
        },
      ]);
    await expect(page.getByText("Hello from DeerFlow!")).toBeVisible({
      timeout: 10_000,
    });
  });

  test("keeps attachments visible while upload submit is pending", async ({
    page,
  }) => {
    let releaseUpload!: () => void;
    const uploadCanFinish = new Promise<void>((resolve) => {
      releaseUpload = resolve;
    });
    let uploadStarted!: () => void;
    const uploadStartedPromise = new Promise<void>((resolve) => {
      uploadStarted = resolve;
    });

    await page.route("**/api/threads/*/uploads", async (route) => {
      uploadStarted();
      await uploadCanFinish;
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          success: true,
          message: "Uploaded",
          files: [
            {
              filename: "report.docx",
              size: 12,
              path: "report.docx",
              virtual_path: "/mnt/user-data/uploads/report.docx",
              artifact_url: "/api/threads/test/uploads/report.docx",
              extension: ".docx",
            },
          ],
        }),
      });
    });

    await page.goto("/workspace/chats/new");

    const textarea = page.getByPlaceholder(/how can i assist you/i);
    await expect(textarea).toBeVisible({ timeout: 15_000 });
    const promptForm = page.locator("form").filter({ has: textarea });

    await page.getByLabel("Upload files").setInputFiles({
      name: "report.docx",
      mimeType:
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
      buffer: Buffer.from("fake docx"),
    });
    await expect(promptForm.getByText("report.docx")).toBeVisible();

    await textarea.fill("Summarize this document");
    await textarea.press("Enter");

    await uploadStartedPromise;
    await expect(promptForm.getByText("report.docx")).toBeVisible();

    releaseUpload();
    await expect(page.getByText("Hello from DeerFlow!")).toBeVisible({
      timeout: 10_000,
    });
    await expect(promptForm.getByText("report.docx")).toBeHidden();
  });

  test("does not fetch follow-up suggestions when disabled in config", async ({
    page,
  }) => {
    await page.route("**/api/suggestions/config", (route) => {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ enabled: false }),
      });
    });

    let suggestionsFetched = false;
    await page.route("**/api/threads/*/suggestions", (route) => {
      suggestionsFetched = true;
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ suggestions: [] }),
      });
    });

    let streamCalled = false;
    await page.route("**/runs/stream", (route) => {
      streamCalled = true;
      return handleRunStream(route);
    });

    await page.goto("/workspace/chats/new");

    const textarea = page.getByPlaceholder(/how can i assist you/i);
    await expect(textarea).toBeVisible({ timeout: 15_000 });

    await textarea.fill("Hello");
    await textarea.press("Enter");

    await expect.poll(() => streamCalled, { timeout: 10_000 }).toBeTruthy();
    await expect(page.getByText("Hello from DeerFlow!")).toBeVisible({
      timeout: 10_000,
    });
    await page.waitForTimeout(1000);
    expect(suggestionsFetched).toBe(false);
  });
});

/**
 * Input suggestions group labels & visibility E2E tests.
 * Dependencies: mockLangGraphAPI(page) must mock auth/me with needs_setup: false,
 * and thread history returning empty [] for new threads.
 */

test.describe("Input suggestion group config", () => {
  test.beforeEach(async ({ page }) => {
    await mockLangGraphAPI(page);
  });

  const baseConfig = {
    appName: "Test",
    appAbbreviation: "Test",
    welcome: { greeting: "Hello", description: "Desc" },
    loginPage: { title: "Test" },
    inputSuggestions: [
      { id: "a", label: "Main-A", prompt: "A", icon: "Monitor", group: "main" },
      { id: "b", label: "Create-B", prompt: "B", icon: "Bug", group: "create" },
    ],
  };

  // E2E-1: 默认 label 为 undefined → 回退 i18n t.common.create（中文 "创建"）
  test("shows i18n fallback '创建' when no label configured", async ({ page }) => {
    await page.route("**/site.config.json", (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(baseConfig) }),
    );
    await page.goto("/workspace/chats/new");
    await expect(page.getByPlaceholder(/how can i assist/i)).toBeVisible({ timeout: 15_000 });
    await expect(page.getByRole("button", { name: "创建" })).toBeVisible({ timeout: 10_000 });
  });

  // E2E-2: 自定义 label
  test("shows custom label when configured", async ({ page }) => {
    await page.route("**/site.config.json", (route) =>
      route.fulfill({
        status: 200, contentType: "application/json",
        body: JSON.stringify({ ...baseConfig, suggestionGroups: { create: { label: "更多", visible: true } } }),
      }),
    );
    await page.goto("/workspace/chats/new");
    await expect(page.getByPlaceholder(/how can i assist/i)).toBeVisible({ timeout: 15_000 });
    await expect(page.getByRole("button", { name: "更多" })).toBeVisible({ timeout: 10_000 });
  });

  // E2E-3: visible=false → 下拉隐藏
  test("hides dropdown when visible=false", async ({ page }) => {
    await page.route("**/site.config.json", (route) =>
      route.fulfill({
        status: 200, contentType: "application/json",
        body: JSON.stringify({ ...baseConfig, suggestionGroups: { create: { visible: false } } }),
      }),
    );
    await page.goto("/workspace/chats/new");
    await expect(page.getByPlaceholder(/how can i assist/i)).toBeVisible({ timeout: 15_000 });
    await expect(page.getByRole("button", { name: "Main-A" })).toBeVisible({ timeout: 10_000 });
    // 下拉按钮完全不在 DOM 中
    await expect(page.getByRole("button", { name: "创建" })).toHaveCount(0);
  });

  // E2E-4: visible=true 显式配置
  test("shows dropdown when visible=true (explicit)", async ({ page }) => {
    await page.route("**/site.config.json", (route) =>
      route.fulfill({
        status: 200, contentType: "application/json",
        body: JSON.stringify({ ...baseConfig, suggestionGroups: { create: { label: "More", visible: true } } }),
      }),
    );
    await page.goto("/workspace/chats/new");
    await expect(page.getByPlaceholder(/how can i assist/i)).toBeVisible({ timeout: 15_000 });
    await expect(page.getByRole("button", { name: "More" })).toBeVisible({ timeout: 10_000 });
  });

  // E2E-5: 空字符串 label → 回退 i18n
  test("falls back to i18n when label is empty string", async ({ page }) => {
    await page.route("**/site.config.json", (route) =>
      route.fulfill({
        status: 200, contentType: "application/json",
        body: JSON.stringify({ ...baseConfig, suggestionGroups: { create: { label: "" } } }),
      }),
    );
    await page.goto("/workspace/chats/new");
    await expect(page.getByPlaceholder(/how can i assist/i)).toBeVisible({ timeout: 15_000 });
    await expect(page.getByRole("button", { name: "创建" })).toBeVisible({ timeout: 10_000 });
  });

  // E2E-6: fetch 失败 → 不崩溃，使用默认
  test("does not crash when site.config fetch fails", async ({ page }) => {
    await page.route("**/site.config.json", (route) => route.abort("internetdisconnected"));
    await page.goto("/workspace/chats/new");
    await expect(page.getByPlaceholder(/how can i assist/i)).toBeVisible({ timeout: 15_000 });
    await expect(page.locator("body")).toBeVisible();
  });

  // E2E-7: HTTP 500 → 不崩溃
  test("does not crash on HTTP 500", async ({ page }) => {
    await page.route("**/site.config.json", (route) =>
      route.fulfill({ status: 500, contentType: "text/plain", body: "Error" }),
    );
    await page.goto("/workspace/chats/new");
    await expect(page.getByPlaceholder(/how can i assist/i)).toBeVisible({ timeout: 15_000 });
  });

  // E2E-8: 畸形 JSON → 不崩溃
  test("does not crash on malformed JSON", async ({ page }) => {
    await page.route("**/site.config.json", (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: "{not valid!!!" }),
    );
    await page.goto("/workspace/chats/new");
    await expect(page.getByPlaceholder(/how can i assist/i)).toBeVisible({ timeout: 15_000 });
  });
});

