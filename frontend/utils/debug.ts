/**
 * Debug utilities for inspecting conversation state.
 * These functions can be called from browser console for debugging.
 */

/**
 * Dump all conversations from localStorage to console.
 * Usage: Open browser console and run: window.dumpConversations()
 */
export const dumpConversations = () => {
  try {
    const stored = localStorage.getItem('netbox-web-chat-conversations')
    if (!stored) {
      console.log('📭 No conversations in localStorage')
      return
    }

    const conversations = JSON.parse(stored)
    console.log('📚 Conversations in localStorage:', conversations.length)

    conversations.forEach((conv: any, index: number) => {
      console.log(`\n--- Conversation ${index + 1} ---`)
      console.log('ID:', conv.id)
      console.log('Title:', conv.title)
      console.log('Created:', new Date(conv.createdAt).toLocaleString())
      console.log('Updated:', new Date(conv.updatedAt).toLocaleString())
      console.log('Messages:', conv.messages.length)

      if (conv.messages.length > 0) {
        conv.messages.forEach((msg: any, msgIndex: number) => {
          console.log(`  Message ${msgIndex + 1} (${msg.role}):`, msg.content.substring(0, 100))
        })
      }
    })

    return conversations
  } catch (error) {
    console.error('❌ Error reading conversations:', error)
  }
}

/**
 * Clear all conversations from localStorage.
 * Usage: window.clearConversations()
 */
export const clearConversationsDebug = () => {
  if (confirm('⚠️ Delete ALL conversations from localStorage?')) {
    localStorage.removeItem('netbox-web-chat-conversations')
    console.log('✅ Cleared all conversations - reload page to reset')
    return true
  }
  return false
}

// Make functions available globally for browser console
if (typeof window !== 'undefined') {
  ;(window as any).dumpConversations = dumpConversations
  ;(window as any).clearConversations = clearConversationsDebug
  console.log('🛠️ Debug utilities loaded. Try:')
  console.log('  window.dumpConversations() - Show all conversations')
  console.log('  window.clearConversations() - Clear localStorage')
}
