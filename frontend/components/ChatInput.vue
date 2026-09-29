<template>
  <div class="chat-input-container">
    <form @submit.prevent="handleSubmit" class="chat-input-form">
      <textarea
        v-model="message"
        @keydown="handleKeyDown"
        :disabled="disabled"
        :placeholder="placeholder"
        class="chat-textarea"
        rows="3"
        ref="textareaRef"
      ></textarea>
      <div class="chat-input-actions">
        <div class="input-hint">
          <LoadingSpinner v-if="isProcessing" size="sm" aria-label="Processing message" />
          <span>{{ hint }}</span>
        </div>
        <div class="button-group">
          <button
            v-if="editMode"
            type="button"
            @click="handleCancel"
            class="cancel-button"
          >
            Cancel
          </button>
          <!-- While a turn runs the primary button becomes Stop (cancels the turn) -->
          <button
            v-if="isProcessing"
            type="button"
            class="stop-button"
            title="Stop the running turn. The model will not remember the partial answer."
            @click="emit('stop')"
          >
            Stop
          </button>
          <button
            v-else
            type="submit"
            :disabled="!canSend"
            class="send-button"
            :class="{ 'send-button-disabled': !canSend }"
          >
            <span v-if="editMode">Update</span>
            <span v-else>Send</span>
          </button>
        </div>
      </div>
    </form>
  </div>
</template>

<script setup lang="ts">
interface Props {
  disabled?: boolean
  isProcessing?: boolean
  placeholder?: string
  editMode?: boolean
  initialValue?: string
}

interface Emits {
  (e: 'send', message: string): void
  (e: 'update', message: string): void
  /** Cancel edit mode. */
  (e: 'cancel'): void
  /** Stop the running turn (server-side cancel). */
  (e: 'stop'): void
}

const props = withDefaults(defineProps<Props>(), {
  disabled: false,
  isProcessing: false,
  placeholder: 'Ask about your NetBox infrastructure...',
  editMode: false,
  initialValue: ''
})

const emit = defineEmits<Emits>()

const message = ref('')
const textareaRef = ref<HTMLTextAreaElement>()

const canSend = computed(() =>
  !props.disabled &&
  !props.isProcessing &&
  message.value.trim().length > 0
)

const hint = computed(() => {
  if (props.isProcessing) {
    return 'Turn in progress (local model; this can take minutes). Press Stop to cancel.'
  }
  if (props.disabled) {
    return 'Chat is disabled'
  }
  return 'Press Enter to send, Shift+Enter for new line'
})

const handleSubmit = () => {
  if (canSend.value) {
    if (props.editMode) {
      emit('update', message.value.trim())
    } else {
      emit('send', message.value.trim())
    }
    message.value = ''
    // Focus textarea after sending
    nextTick(() => {
      textareaRef.value?.focus()
    })
  }
}

const handleCancel = () => {
  message.value = ''
  emit('cancel')
}

const handleKeyDown = (event: KeyboardEvent) => {
  // Send on Enter, unless Shift is held
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    handleSubmit()
  }
}

// Watch for edit mode changes and populate with initial value
watch(() => props.editMode, (isEditing) => {
  if (isEditing && props.initialValue) {
    message.value = props.initialValue
    nextTick(() => {
      textareaRef.value?.focus()
      // Select all text for easy editing
      textareaRef.value?.select()
    })
  }
})

// Auto-focus on mount
onMounted(() => {
  textareaRef.value?.focus()
})
</script>

<style scoped>
.chat-input-container {
  @apply border-t border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 p-4;
}

.chat-input-form {
  @apply space-y-2;
}

.chat-textarea {
  @apply w-full p-3 border border-gray-300 dark:border-gray-600 rounded-lg;
  @apply bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100;
  @apply focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 focus:border-transparent;
  @apply resize-none transition-colors;
  @apply placeholder-gray-500 dark:placeholder-gray-400;
}

.chat-textarea:disabled {
  @apply bg-gray-100 dark:bg-gray-800 cursor-not-allowed opacity-60;
}

.chat-input-actions {
  @apply flex justify-between items-center;
}

.input-hint {
  @apply flex items-center gap-2;
  @apply text-sm text-gray-500 dark:text-gray-400;
}

.button-group {
  @apply flex gap-2;
}

.send-button {
  @apply px-4 py-2 bg-blue-600 text-white rounded-lg font-medium;
  @apply hover:bg-blue-700 active:bg-blue-800 transition-colors;
  @apply focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2;
}

.send-button-disabled {
  @apply bg-gray-400 dark:bg-gray-600 cursor-not-allowed;
  @apply hover:bg-gray-400 dark:hover:bg-gray-600;
}

.stop-button {
  @apply px-4 py-2 bg-red-600 text-white rounded-lg font-medium;
  @apply hover:bg-red-700 active:bg-red-800 transition-colors;
  @apply focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-2;
}

.cancel-button {
  @apply px-4 py-2 bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-lg font-medium;
  @apply hover:bg-gray-300 dark:hover:bg-gray-600 active:bg-gray-400 dark:active:bg-gray-500 transition-colors;
  @apply focus:outline-none focus:ring-2 focus:ring-gray-400 focus:ring-offset-2;
}
</style>