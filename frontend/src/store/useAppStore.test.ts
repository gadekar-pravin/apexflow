import { describe, it, expect, beforeEach } from 'vitest'
import { useAppStore } from './useAppStore'

describe('useAppStore', () => {
  beforeEach(() => {
    // Reset store to initial state before each test
    useAppStore.setState({
      theme: 'light',
      selectedRunId: null,
      selectedNodeId: null,
      selectedDocumentPath: null,
      selectedDocumentName: null,
    })
  })

  describe('initial state', () => {
    it('has light theme by default', () => {
      expect(useAppStore.getState().theme).toBe('light')
    })

    it('has no selections by default', () => {
      const state = useAppStore.getState()
      expect(state.selectedRunId).toBeNull()
      expect(state.selectedNodeId).toBeNull()
      expect(state.selectedDocumentPath).toBeNull()
    })
  })

  describe('theme actions', () => {
    it('setTheme updates theme to dark', () => {
      useAppStore.getState().setTheme('dark')
      expect(useAppStore.getState().theme).toBe('dark')
    })

    it('setTheme updates theme to system', () => {
      useAppStore.getState().setTheme('system')
      expect(useAppStore.getState().theme).toBe('system')
    })

    it('setTheme updates theme to light', () => {
      useAppStore.getState().setTheme('dark')
      useAppStore.getState().setTheme('light')
      expect(useAppStore.getState().theme).toBe('light')
    })

    it('setTheme applies dark class to document when dark', () => {
      const root = document.documentElement

      useAppStore.getState().setTheme('dark')
      expect(root.classList.contains('dark')).toBe(true)

      useAppStore.getState().setTheme('light')
      expect(root.classList.contains('dark')).toBe(false)
    })

    it('setTheme respects system preference when system', () => {
      // matchMedia is mocked in setup.ts to return matches: false (light mode)
      useAppStore.getState().setTheme('system')
      expect(document.documentElement.classList.contains('dark')).toBe(false)
    })
  })

  describe('selection actions', () => {
    it('setSelectedRunId updates run selection', () => {
      useAppStore.getState().setSelectedRunId('run-123')
      expect(useAppStore.getState().selectedRunId).toBe('run-123')
    })

    it('setSelectedRunId clears node selection', () => {
      useAppStore.getState().setSelectedNodeId('node-1')
      expect(useAppStore.getState().selectedNodeId).toBe('node-1')

      useAppStore.getState().setSelectedRunId('run-456')
      expect(useAppStore.getState().selectedNodeId).toBeNull()
    })

    it('setSelectedRunId can clear selection with null', () => {
      useAppStore.getState().setSelectedRunId('run-123')
      useAppStore.getState().setSelectedRunId(null)
      expect(useAppStore.getState().selectedRunId).toBeNull()
    })

    it('setSelectedNodeId updates node selection', () => {
      useAppStore.getState().setSelectedNodeId('node-1')
      expect(useAppStore.getState().selectedNodeId).toBe('node-1')
    })

    it('setSelectedNodeId does not affect run selection', () => {
      useAppStore.getState().setSelectedRunId('run-123')
      useAppStore.getState().setSelectedNodeId('node-1')
      expect(useAppStore.getState().selectedRunId).toBe('run-123')
    })

    it('setSelectedDocumentPath updates document selection', () => {
      useAppStore.getState().setSelectedDocumentPath('/docs/readme.md', 'readme.md')
      expect(useAppStore.getState().selectedDocumentPath).toBe('/docs/readme.md')
      expect(useAppStore.getState().selectedDocumentName).toBe('readme.md')
    })

    it('setSelectedDocumentPath can clear selection', () => {
      useAppStore.getState().setSelectedDocumentPath('/docs/file.txt', 'file.txt')
      useAppStore.getState().setSelectedDocumentPath(null)
      expect(useAppStore.getState().selectedDocumentPath).toBeNull()
      expect(useAppStore.getState().selectedDocumentName).toBeNull()
    })
  })

  describe('state isolation', () => {
    it('actions only affect their specific state', () => {
      useAppStore.getState().setSelectedRunId('run-1')
      useAppStore.getState().setSelectedDocumentPath('/doc.md', 'doc.md')

      // Verify all states are independent
      expect(useAppStore.getState().selectedRunId).toBe('run-1')
      expect(useAppStore.getState().selectedDocumentPath).toBe('/doc.md')
      expect(useAppStore.getState().selectedNodeId).toBeNull()
    })
  })
})
