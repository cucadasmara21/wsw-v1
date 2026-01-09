import React from 'react'

export default function StatusCard({title, children}:{title:string; children:React.ReactNode}){
  return (
    <div style={{border:'1px solid #ddd', padding:12, borderRadius:6, marginBottom:12, background:'#fff'}}>
      <h3 style={{margin:'0 0 8px 0'}}>{title}</h3>
      <div>{children}</div>
    </div>
  )
}
