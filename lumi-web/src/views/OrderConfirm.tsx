import { defineComponent, ref, computed, onMounted } from 'vue'
import { orderApi, configApi } from '../api'

/** 待配送条目（本地暂存） */
interface DraftItem {
  drink: string
  floor: number
  room: string
}

export default defineComponent({
  name: 'OrderConfirm',
  setup() {
    // ---------- 表单状态（从服务器加载） ----------
    const drinkOptions = ref<string[]>([])
    const floors = ref<number[]>([])
    const roomsByFloor = ref<Record<number, string[]>>({})

    /** 从服务器加载配置选项 */
    const loadOptions = async () => {
      try {
        const res = await configApi.getOptions()
        const data = res.data
        drinkOptions.value = data.drinks || []
        floors.value = data.floors || []
        // 将 rooms 的 key 从 string 转为 number
        const rooms: Record<number, string[]> = {}
        for (const [k, v] of Object.entries(data.rooms || {})) {
          rooms[Number(k)] = v as string[]
        }
        roomsByFloor.value = rooms

        // 初始化默认选中
        if (drinkOptions.value.length > 0) {
          selectedDrink.value = drinkOptions.value[0]
        }
        if (floors.value.length > 0) {
          floorInput.value = floors.value[0]
          const firstRooms = rooms[floors.value[0]]
          if (firstRooms && firstRooms.length > 0) {
            roomInput.value = firstRooms[0]
          }
        }
      } catch (e) {
        console.error('加载配置选项失败', e)
      }
    }

    onMounted(loadOptions)

    const selectedDrink = ref('')
    const floorInput = ref(1)
    const roomInput = ref('')
    const maxPerDelivery = ref(3)

    // ---------- 待送出列表 ----------
    const draftItems = ref<DraftItem[]>([])

    /** 按目标（楼层+房间）分组 */
    const groupedDrafts = computed(() => {
      const map = new Map<string, { floor: number; room: string; drinks: string[] }>()
      for (const item of draftItems.value) {
        const key = `${item.floor}F-${item.room}`
        if (!map.has(key)) {
          map.set(key, { floor: item.floor, room: item.room, drinks: [] })
        }
        map.get(key)!.drinks.push(item.drink)
      }
      return Array.from(map.entries())
    })

    /** 当前楼层可选房间列表 */
    const roomsForCurrentFloor = computed(() => {
      return roomsByFloor.value[floorInput.value] || ['101']
    })

    /** 楼层切换时重置房间为该层第一个 */
    const onFloorChange = (floor: number) => {
      floorInput.value = floor
      const rooms = roomsByFloor.value[floor]
      roomInput.value = rooms && rooms.length > 0 ? rooms[0] : ''
    }

    /** 是否可以添加 */
    const canAdd = computed(() => {
      return roomInput.value.trim() !== '' && draftItems.value.length < maxPerDelivery.value
    })

    /** 添加一杯到待送出列表 */
    const addItem = () => {
      if (!canAdd.value) return
      draftItems.value.push({
        drink: selectedDrink.value,
        floor: floorInput.value,
        room: roomInput.value.trim(),
      })
    }

    /** 从列表中移除一项 */
    const removeItem = (index: number) => {
      draftItems.value.splice(index, 1)
    }

    /** 清空列表 */
    const clearAll = () => {
      if (draftItems.value.length === 0) return
      if (confirm('确定清空所有待配送饮品？')) {
        draftItems.value = []
      }
    }

    // ---------- 送出 ----------
    const dispatching = ref(false)
    const dispatchResult = ref<'success' | 'error' | null>(null)

    const dispatch = async () => {
      if (draftItems.value.length === 0) return
      dispatching.value = true
      dispatchResult.value = null
      try {
        await orderApi.dispatch(draftItems.value)
        dispatchResult.value = 'success'
        draftItems.value = []
        setTimeout(() => (dispatchResult.value = null), 3000)
      } catch (e) {
        console.error('送出失败', e)
        dispatchResult.value = 'error'
        setTimeout(() => (dispatchResult.value = null), 3000)
      } finally {
        dispatching.value = false
      }
    }

    return () => (
      <div>
        <div class="page-header">
          <h2>📋 配送录入</h2>
          <p>手动添加饮品和目标房间信息，点击「送出」后 Lumi 开始配送</p>
        </div>

        {/* 录入表单 */}
        <div class="card">
          <div class="card-title">添加饮品</div>

          <div style="display: grid; grid-template-columns: 1fr 120px 140px auto; gap: 12px; align-items: end">
            <div class="form-group" style="margin-bottom: 0">
              <label class="form-label">饮品</label>
              <select
                class="form-select"
                value={selectedDrink.value}
                onChange={(e: Event) => (selectedDrink.value = (e.target as HTMLSelectElement).value)}
              >
                {drinkOptions.value.map((d) => (
                  <option key={d} value={d}>{d}</option>
                ))}
              </select>
            </div>

            <div class="form-group" style="margin-bottom: 0">
              <label class="form-label">楼层</label>
              <select
                class="form-select"
                value={floorInput.value}
                onChange={(e: Event) => onFloorChange(Number((e.target as HTMLSelectElement).value))}
              >
                {floors.value.map((f) => (
                  <option key={f} value={f}>{f}F</option>
                ))}
              </select>
            </div>

            <div class="form-group" style="margin-bottom: 0">
              <label class="form-label">房间号</label>
              <select
                class="form-select"
                value={roomInput.value}
                onChange={(e: Event) => (roomInput.value = (e.target as HTMLSelectElement).value)}
              >
                {roomsForCurrentFloor.value.map((r) => (
                  <option key={r} value={r}>{r}</option>
                ))}
              </select>
            </div>

            <button
              class="btn btn-primary"
              disabled={!canAdd.value}
              onClick={addItem}
              style="height: 42px"
            >
              + 添加
            </button>
          </div>

          <div style="display: flex; align-items: center; gap: 16px; margin-top: 16px; font-size: 13px; color: var(--text-secondary)">
            <div style="display: flex; align-items: center; gap: 6px">
              <label class="form-label" style="margin-bottom: 0; white-space: nowrap">单次配送上限</label>
              <input
                class="form-input"
                type="number"
                min={1}
                max={10}
                value={maxPerDelivery.value}
                onInput={(e: Event) => (maxPerDelivery.value = Math.max(1, Math.min(10, Number((e.target as HTMLInputElement).value) || 1)))}
                style="width: 70px; padding: 6px 10px; text-align: center"
              />
              <span>杯</span>
            </div>
            <span>已添加 {draftItems.value.length} / {maxPerDelivery.value}</span>
          </div>
        </div>

        {/* 待送出列表 */}
        <div class="card">
          <div class="card-title">
            <span>待送出 ({draftItems.value.length} 杯)</span>
            {draftItems.value.length > 0 && (
              <button class="btn btn-outline btn-sm" onClick={clearAll} style="margin-left: auto">
                清空
              </button>
            )}
          </div>

          {draftItems.value.length === 0 ? (
            <div class="empty-state">
              <div class="empty-state-icon">☕</div>
              <p>请在上方添加饮品</p>
            </div>
          ) : (
            <div style="display: flex; flex-direction: column; gap: 12px">
              {groupedDrafts.value.map(([key, group]) => (
                <div
                  key={key}
                  style="display: flex; align-items: center; gap: 16px; padding: 14px 16px; background: #f8fafc; border-radius: 10px; border: 1px solid var(--border)"
                >
                  <div style="min-width: 60px; font-weight: 700; font-size: 15px; color: var(--primary)">
                    {group.floor}F-{group.room}
                  </div>
                  <div style="flex: 1; display: flex; flex-wrap: wrap; gap: 6px">
                    {group.drinks.map((drink, i) => (
                      <span
                        key={i}
                        class="badge badge-queued"
                        style="font-size: 13px; padding: 5px 12px"
                      >
                        {drink}
                      </span>
                    ))}
                  </div>
                  <div style="font-size: 12px; color: var(--text-secondary)">
                    {group.drinks.length} 杯
                  </div>
                </div>
              ))}

              {/* 明细列表 */}
              <div class="table-wrapper" style="margin-top: 4px">
                <table>
                  <thead>
                    <tr>
                      <th style="width: 40px">#</th>
                      <th>饮品</th>
                      <th>目标</th>
                      <th style="width: 60px"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {draftItems.value.map((item, index) => (
                      <tr key={index}>
                        <td style="color: var(--text-secondary)">{index + 1}</td>
                        <td>{item.drink}</td>
                        <td>{item.floor}F-{item.room}</td>
                        <td>
                          <button
                            class="btn btn-outline btn-sm"
                            onClick={() => removeItem(index)}
                            style="color: var(--danger); border-color: transparent"
                          >
                            移除
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>

        {/* 送出按钮 */}
        <div style="position: sticky; bottom: 0; padding: 16px 0; background: linear-gradient(transparent, var(--bg) 20%)">
          <div style="display: flex; align-items: center; gap: 16px">
            <button
              class="btn btn-success"
              disabled={draftItems.value.length === 0 || dispatching.value}
              onClick={dispatch}
              style="flex: 1; height: 52px; font-size: 16px; font-weight: 600; border-radius: 12px"
            >
              {dispatching.value
                ? '正在送出...'
                : `🚀 送出（${draftItems.value.length} 杯）`
              }
            </button>
          </div>

          {/* 送出结果提示 */}
          {dispatchResult.value === 'success' && (
            <div style="margin-top: 12px; padding: 12px 16px; background: #d1fae5; border-radius: 8px; color: #065f46; font-weight: 500">
              ✅ 已送出！Lumi 正在准备配送
            </div>
          )}
          {dispatchResult.value === 'error' && (
            <div style="margin-top: 12px; padding: 12px 16px; background: #fee2e2; border-radius: 8px; color: #991b1b; font-weight: 500">
              ❌ 送出失败，请重试
            </div>
          )}
        </div>
      </div>
    )
  },
})
