import type { ReactNode } from 'react'

import { cx } from '../../lib/cx'

export function Table({ head, children, className }: {
  head: ReactNode[]
  children: ReactNode
  className?: string
}) {
  return (
    <div className={cx('overflow-x-auto', className)}>
      <table className="w-full border-collapse text-left text-[11.5px]">
        <thead>
          <tr className="border-b border-[var(--color-line)]">
            {head.map((cell, index) => (
              <th
                key={index}
                className="whitespace-nowrap px-3 py-2 text-[9.5px] font-medium uppercase tracking-[0.12em] text-faint"
              >
                {cell}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  )
}

export function Row({ children, onClick, className }: {
  children: ReactNode
  onClick?: () => void
  className?: string
}) {
  return (
    <tr
      onClick={onClick}
      className={cx(
        'border-b border-[var(--color-line)] last:border-0',
        onClick && 'cursor-pointer hover:bg-[var(--overlay-1)]',
        className,
      )}
    >
      {children}
    </tr>
  )
}

export function Cell({ children, className }: { children: ReactNode; className?: string }) {
  return <td className={cx('whitespace-nowrap px-3 py-2 align-middle', className)}>{children}</td>
}
