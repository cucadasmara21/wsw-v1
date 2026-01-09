import React from 'react'

export default function TableList<T>({columns, rows, renderCell}:{
  columns: string[]
  rows: T[]
  renderCell: (row:T, col:string)=>React.ReactNode
}){
  if (rows.length === 0) return <div>No rows</div>
  return (
    <table style={{width:'100%', borderCollapse:'collapse'}}>
      <thead>
        <tr>
          {columns.map(c=> <th key={c} style={{textAlign:'left', borderBottom:'1px solid #eee', padding:'8px'}}>{c}</th>)}
        </tr>
      </thead>
      <tbody>
        {rows.map((r, i)=> (
          <tr key={i}>
            {columns.map(c=> <td key={c} style={{padding:'8px', borderBottom:'1px solid #f6f6f6'}}>{renderCell(r,c)}</td>)}
          </tr>
        ))}
      </tbody>
    </table>
  )
}
