import { useEffect, useState } from 'react'
import { getJson } from '../lib/api.js'

// GET simples com estado; `key` muda -> refaz a chamada
export function useApi(path, params) {
  const key = JSON.stringify(params ?? {})
  const [state, setState] = useState({ status: 'loading', data: null })

  useEffect(() => {
    let alive = true
    setState((s) => ({ ...s, status: 'loading' }))
    getJson(path, params)
      .then((data) => alive && setState({ status: 'ready', data }))
      .catch((err) => alive && setState({ status: 'error', data: null, error: err.message }))
    return () => {
      alive = false
    }
  }, [path, key])

  return state
}
