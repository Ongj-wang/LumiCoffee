import { defineComponent, ref, onMounted, onUnmounted } from 'vue'
import { calibApi, type CalibSample, type CalibResult } from '../api'

export default defineComponent({
  name: 'VisionCalib',
  setup() {
    // ---------- 状态 ----------
    const previewSrc = ref<string>('')
    const samples = ref<CalibSample[]>([])
    const sampleCount = ref(0)
    const minRequired = ref(8)
    const result = ref<CalibResult | null>(null)
    const resultSource = ref<string>('')
    const hasResult = ref(false)

    const capturing = ref(false)
    const running = ref(false)
    const message = ref('')
    const messageType = ref<'info' | 'success' | 'error'>('info')

    let previewTimer: ReturnType<typeof setInterval> | null = null

    // ---------- 预览 ----------
    const refreshPreview = async () => {
      try {
        const res = await calibApi.getPreview()
        previewSrc.value = res.data.preview
      } catch {
        // 静默失败
      }
    }

    const startPreview = () => {
      refreshPreview()
      previewTimer = setInterval(refreshPreview, 2000)
    }

    const stopPreview = () => {
      if (previewTimer) {
        clearInterval(previewTimer)
        previewTimer = null
      }
    }

    // ---------- 采集 ----------
    const onCapture = async () => {
      capturing.value = true
      message.value = ''
      try {
        const res = await calibApi.capture()
        const d = res.data
        sampleCount.value = d.sample_count
        if (d.preview) previewSrc.value = d.preview
        if (d.success) {
          messageType.value = 'success'
          message.value = d.message
          await loadSamples()
        } else {
          messageType.value = 'error'
          message.value = d.message || '角点检测失败，请调整标定板位置'
        }
      } catch (e: any) {
        messageType.value = 'error'
        message.value = '采集失败: ' + (e?.message || '未知错误')
      } finally {
        capturing.value = false
      }
    }

    // ---------- 数据列表 ----------
    const loadSamples = async () => {
      try {
        const res = await calibApi.getSamples()
        samples.value = res.data.samples
        sampleCount.value = res.data.count
        minRequired.value = res.data.min_required
      } catch {
        // ignore
      }
    }

    const onClear = async () => {
      if (!confirm('确定清空所有采集数据？')) return
      try {
        await calibApi.clearSamples()
        samples.value = []
        sampleCount.value = 0
        message.value = '已清空采集数据'
        messageType.value = 'info'
      } catch {
        // ignore
      }
    }

    // ---------- 标定 ----------
    const onRun = async () => {
      running.value = true
      message.value = '正在计算标定参数...'
      messageType.value = 'info'
      try {
        const res = await calibApi.run()
        const d = res.data
        if (d.success && d.result) {
          result.value = d.result
          hasResult.value = true
          resultSource.value = '本次标定'
          messageType.value = 'success'
          message.value = d.message
        } else {
          messageType.value = 'error'
          message.value = d.message || '标定失败'
        }
      } catch (e: any) {
        messageType.value = 'error'
        message.value = '标定异常: ' + (e?.message || '未知错误')
      } finally {
        running.value = false
      }
    }

    // ---------- 标定结果 ----------
    const loadResult = async () => {
      try {
        const res = await calibApi.getResult()
        hasResult.value = res.data.has_result
        if (res.data.result) {
          result.value = res.data.result
          resultSource.value = res.data.source === 'file' ? '已加载文件' : '本次标定'
        }
      } catch {
        // ignore
      }
    }

    // ---------- 生命周期 ----------
    onMounted(() => {
      loadSamples()
      loadResult()
      startPreview()
    })

    onUnmounted(() => {
      stopPreview()
    })

    return () => (
      <div class="calib-page">
        <div class="calib-header">
          <h2>视觉手眼标定</h2>
          <p class="calib-desc">
            将标定板放在相机视野中，调整机械臂到不同位姿后点击「采集」。
            至少采集 {minRequired.value} 组数据后可运行标定。
          </p>
        </div>

        {/* 消息提示 */}
        {message.value && (
          <div class={`calib-msg calib-msg-${messageType.value}`}>
            {message.value}
          </div>
        )}

        <div class="calib-body">
          {/* 左侧：相机预览 + 操作 */}
          <div class="calib-left">
            <div class="calib-preview-box">
              {previewSrc.value ? (
                <img src={previewSrc.value} alt="相机预览" class="calib-preview-img" />
              ) : (
                <div class="calib-preview-placeholder">等待相机连接...</div>
              )}
            </div>

            <div class="calib-actions">
              <button
                class="btn btn-primary"
                onClick={onCapture}
                disabled={capturing.value}
              >
                {capturing.value ? '采集中...' : '采集数据'}
              </button>
              <button
                class="btn btn-success"
                onClick={onRun}
                disabled={running.value || sampleCount.value < minRequired.value}
              >
                {running.value ? '标定中...' : '运行标定'}
              </button>
              <button class="btn btn-danger" onClick={onClear} disabled={sampleCount.value === 0}>
                清空数据
              </button>
            </div>

            <div class="calib-count">
              已采集 <strong>{sampleCount.value}</strong> / {minRequired.value} 组（最少）
            </div>
          </div>

          {/* 右侧：采集列表 + 结果 */}
          <div class="calib-right">
            {/* 采集缩略图 */}
            <div class="calib-section">
              <h3>采集数据 ({samples.value.length})</h3>
              <div class="calib-samples-grid">
                {samples.value.map((s) => (
                  <div class="calib-sample-card" key={s.index}>
                    <img src={s.preview} alt={`样本 ${s.index + 1}`} />
                    <div class="calib-sample-info">
                      <span>#{s.index + 1}</span>
                      <span class="calib-pose">
                        [{s.pose.map((p) => p.toFixed(1)).join(', ')}]
                      </span>
                    </div>
                  </div>
                ))}
                {samples.value.length === 0 && (
                  <div class="calib-empty">暂无采集数据</div>
                )}
              </div>
            </div>

            {/* 标定结果 */}
            <div class="calib-section">
              <h3>标定结果 {resultSource.value && `(${resultSource.value})`}</h3>
              {hasResult.value && result.value ? (
                <div class="calib-result">
                  <details>
                    <summary>相机内参 (CameraMatrix)</summary>
                    <pre>{JSON.stringify(result.value.CameraMatrix, null, 2)}</pre>
                  </details>
                  <details>
                    <summary>畸变系数 (DistCoeffs)</summary>
                    <pre>{JSON.stringify(result.value.CameraDistCoeffs, null, 2)}</pre>
                  </details>
                  <details>
                    <summary>旋转矩阵 (RotationMat)</summary>
                    <pre>{JSON.stringify(result.value.RotationMat, null, 2)}</pre>
                  </details>
                  <details>
                    <summary>平移向量 (TranslationMat)</summary>
                    <pre>{JSON.stringify(result.value.TranslationMat, null, 2)}</pre>
                  </details>
                </div>
              ) : (
                <div class="calib-empty">暂无标定结果</div>
              )}
            </div>
          </div>
        </div>
      </div>
    )
  },
})
