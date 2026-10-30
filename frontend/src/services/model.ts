import { appConfig } from '@/config/env'
import { apiRequest } from '@/services/apiClient'

export interface ModelEvaluationMetrics {
  modelName: string
  architecture: string
  mae: number | null
  rmse: number | null
  pearsonR: number | null
  datasetEvaluated: string
  nTestSamples: number | null
  biasCorrected: boolean
  lastEvaluated: string | null
}

export const modelMetricsService = {
  async getMetrics(): Promise<ModelEvaluationMetrics> {
    if (appConfig.isDemoMode) {
      return {
        modelName: 'No verified model metrics',
        architecture: 'Unavailable',
        mae: null,
        rmse: null,
        pearsonR: null,
        datasetEvaluated: 'Unavailable',
        nTestSamples: null,
        biasCorrected: false,
        lastEvaluated: null,
      }
    }

    const response = await apiRequest<{
      data?: Partial<ModelEvaluationMetrics>
      metrics?: Partial<ModelEvaluationMetrics>
      model?: Partial<ModelEvaluationMetrics>
    }>('/api/v1/model/metrics', { method: 'GET' })

    const payload = (response.data ??
      response.metrics ??
      response.model ??
      response) as Partial<ModelEvaluationMetrics> & Record<string, unknown>
    if (!payload || typeof payload !== 'object') {
      throw new Error('The model metrics response was empty or malformed.')
    }

    return {
      modelName: String(payload.modelName ?? payload.model_name ?? 'Unknown model'),
      architecture: String(payload.architecture ?? 'Unknown architecture'),
      mae: payload.mae == null ? null : Number(payload.mae),
      rmse: payload.rmse == null ? null : Number(payload.rmse),
      pearsonR:
        (payload.pearsonR ?? payload.pearson_r) == null
          ? null
          : Number(payload.pearsonR ?? payload.pearson_r),
      datasetEvaluated: String(
        payload.datasetEvaluated ??
          payload.dataset_name ??
          payload.evaluation_dataset ??
          payload.dataset_evaluated ??
          'Not yet evaluated',
      ),
      nTestSamples:
        (payload.nTestSamples ?? payload.n_test_samples) == null
          ? null
          : Number(payload.nTestSamples ?? payload.n_test_samples),
      biasCorrected: Boolean(payload.biasCorrected ?? payload.bias_corrected),
      lastEvaluated:
        typeof (payload.lastEvaluated ?? payload.last_evaluated) === 'string'
          ? String(payload.lastEvaluated ?? payload.last_evaluated)
          : null,
    }
  },
}
