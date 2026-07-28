/** 厂商元数据（数据来源: providers.json / API） */
export interface ProviderMeta {
  id: string;
  name: string;
  envPrefix: string;
  deepragProviderId: string;
  defaultBaseUrl: string;
  defaultModels: string[];
}

/**
 * 从 API ProviderInfo 提取 ProviderMeta。
 * 后端 REST API 现在返回完整的元数据字段（env_prefix、deeprag_provider_id 等），
 * 前端不再需要硬编码 PROVIDERS 数组。
 */
export function toProviderMeta(info: {
  id: string;
  name: string;
  env_prefix: string;
  deeprag_provider_id: string;
  default_base_url: string;
  default_models: string[];
}): ProviderMeta {
  return {
    id: info.id,
    name: info.name,
    envPrefix: info.env_prefix,
    deepragProviderId: info.deeprag_provider_id,
    defaultBaseUrl: info.default_base_url,
    defaultModels: info.default_models,
  };
}
