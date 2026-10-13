import type { ReactNode } from 'react'
import { ActionContext, type ActionContextValue } from './useUIAction'

export function ActionProvider({
  dispatch,
  disabled,
  children,
}: ActionContextValue & { children: ReactNode }) {
  return <ActionContext.Provider value={{ dispatch, disabled }}>{children}</ActionContext.Provider>
}
