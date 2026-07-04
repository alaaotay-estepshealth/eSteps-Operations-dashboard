import { reactive } from 'vue'

const state = reactive({
  message: '',
  type: 'ok',
  visible: false,
})

let hideTimer = null

export function useToast() {
  return {
    state,
    show(message, type = 'ok', ttl = 2000) {
      state.message = message
      state.type = type
      state.visible = true
      if (hideTimer) clearTimeout(hideTimer)
      hideTimer = setTimeout(() => {
        state.visible = false
      }, ttl)
    },
    hide() {
      if (hideTimer) clearTimeout(hideTimer)
      state.visible = false
    },
  }
}
