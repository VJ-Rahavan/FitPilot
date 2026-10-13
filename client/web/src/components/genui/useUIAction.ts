import { createContext, useContext } from 'react'
import type { UIEventInput } from '../../types/chat'

export interface ActionContextValue {
  /** Send a UI interaction (button click / form submit) back to the assistant. */
  dispatch: (event: UIEventInput) => void
  /** True while the assistant is busy; interactive components should disable themselves. */
  disabled: boolean
}

export const ActionContext = createContext<ActionContextValue>({
  dispatch: () => {},
  disabled: true,
})

export const useUIAction = () => useContext(ActionContext)
