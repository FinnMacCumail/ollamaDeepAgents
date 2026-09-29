/**
 * LocalStorage utility functions for persisting conversations.
 * Provides type-safe storage with error handling.
 */

/**
 * Get item from localStorage with JSON parsing.
 */
export const getItem = <T>(key: string, defaultValue: T): T => {
  if (typeof window === 'undefined') {
    return defaultValue
  }

  try {
    const item = window.localStorage.getItem(key)
    return item ? JSON.parse(item) : defaultValue
  } catch (error) {
    console.error(`Error reading from localStorage key "${key}":`, error)
    return defaultValue
  }
}

/**
 * Set item in localStorage with JSON stringification.
 */
export const setItem = <T>(key: string, value: T): boolean => {
  if (typeof window === 'undefined') {
    return false
  }

  try {
    window.localStorage.setItem(key, JSON.stringify(value))
    return true
  } catch (error) {
    console.error(`Error writing to localStorage key "${key}":`, error)
    return false
  }
}

/**
 * Remove item from localStorage.
 */
export const removeItem = (key: string): boolean => {
  if (typeof window === 'undefined') {
    return false
  }

  try {
    window.localStorage.removeItem(key)
    return true
  } catch (error) {
    console.error(`Error removing localStorage key "${key}":`, error)
    return false
  }
}

/**
 * Clear all items from localStorage.
 */
export const clear = (): boolean => {
  if (typeof window === 'undefined') {
    return false
  }

  try {
    window.localStorage.clear()
    return true
  } catch (error) {
    console.error('Error clearing localStorage:', error)
    return false
  }
}