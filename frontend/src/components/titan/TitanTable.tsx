import { ReactNode } from 'react'

interface TitanTableProps {
  headers: string[]
  children: ReactNode
}

export function TitanTable({ headers, children }: TitanTableProps) {
  return (
    <table className="titan-table">
      <thead>
        <tr>
          {headers.map((header, idx) => (
            <th key={idx}>{header}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {children}
      </tbody>
    </table>
  )
}
