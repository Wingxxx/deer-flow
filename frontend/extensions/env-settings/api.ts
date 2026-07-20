import { fetch } from "@/core/api/fetcher";
import { getBackendBaseURL } from "@/core/config";

import type {
  ProviderSettingsResponse,
  ProviderSettingsUpdateRequest,
  EnvSettingsUpdateResponse,
  VerifyResponse,
  DeleteResponse,
  DeepragCurrentProviderResponse,
  DeepragSwitchResponse,
} from "./types";

export async function loadProviderSettings(): Promise<ProviderSettingsResponse> {
  const response = await fetch(`${getBackendBaseURL()}/api/env-settings/providers`);
  return response.json() as Promise<ProviderSettingsResponse>;
}

export async function updateProviderSetting(
  data: ProviderSettingsUpdateRequest,
): Promise<EnvSettingsUpdateResponse> {
  const response = await fetch(`${getBackendBaseURL()}/api/env-settings/providers`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail ?? "Failed to save API Key");
  }
  return response.json() as Promise<EnvSettingsUpdateResponse>;
}

export async function deleteProviderSetting(
  provider: string,
): Promise<DeleteResponse> {
  const response = await fetch(
    `${getBackendBaseURL()}/api/env-settings/providers/${encodeURIComponent(provider)}`,
    { method: "DELETE" },
  );
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail ?? "Failed to delete API Key");
  }
  return response.json() as Promise<DeleteResponse>;
}

export async function verifyProviderKey(
  provider: string,
  apiKey?: string,
  baseUrl?: string,
): Promise<VerifyResponse> {
  const response = await fetch(
    `${getBackendBaseURL()}/api/env-settings/providers/${encodeURIComponent(provider)}/verify`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ api_key: apiKey, base_url: baseUrl }),
    },
  );
  return response.json() as Promise<VerifyResponse>;
}

export async function getDeepragCurrentProvider(): Promise<DeepragCurrentProviderResponse> {
  const response = await fetch(`${getBackendBaseURL()}/api/env-settings/deeprag/current-provider`);
  return response.json() as Promise<DeepragCurrentProviderResponse>;
}

export async function switchDeepragProvider(
  provider: string,
): Promise<DeepragSwitchResponse> {
  const response = await fetch(`${getBackendBaseURL()}/api/env-settings/deeprag/switch-provider`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ provider }),
  });
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail ?? "Failed to switch DeepRAG provider");
  }
  return response.json() as Promise<DeepragSwitchResponse>;
}
