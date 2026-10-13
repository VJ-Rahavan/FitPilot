import {
  Activity,
  CalendarDays,
  Dumbbell,
  Flame,
  HeartPulse,
  Scale,
  Target,
  Timer,
  Trophy,
  Zap,
  type LucideIcon,
} from 'lucide-react'
import type { IconName } from '../types/ui'

export const ICONS: Record<IconName, LucideIcon> = {
  dumbbell: Dumbbell,
  flame: Flame,
  trophy: Trophy,
  activity: Activity,
  scale: Scale,
  calendar: CalendarDays,
  timer: Timer,
  heart: HeartPulse,
  target: Target,
  zap: Zap,
}
