/** IndexedDB-backed offline outbox for "Report a sighting" — docs/03-UX-
 * DESIGN.md §5: "queued offline and synced when connectivity returns."
 *
 * A queued report is written here the instant the officer taps submit,
 * before any network call happens. A background sync loop (started once,
 * from FieldApp) drains the queue whenever the browser is online, retrying
 * failed items on the next `online` event or the next periodic tick —
 * never silently dropping a report because one upload attempt failed. */

const DB_NAME = 'sentinel-field-outbox'
const STORE_NAME = 'sightings'
const DB_VERSION = 1

export interface QueuedSighting {
  clientReportId: string
  plateText: string
  lat: number | null
  lon: number | null
  notes: string | null
  photoBlob: Blob | null
  queuedAt: string
  attempts: number
  lastError: string | null
}

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION)
    request.onupgradeneeded = () => {
      const db = request.result
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        db.createObjectStore(STORE_NAME, { keyPath: 'clientReportId' })
      }
    }
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error)
  })
}

export async function enqueueSighting(entry: QueuedSighting): Promise<void> {
  const db = await openDb()
  await new Promise<void>((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, 'readwrite')
    tx.objectStore(STORE_NAME).put(entry)
    tx.oncomplete = () => resolve()
    tx.onerror = () => reject(tx.error)
  })
  db.close()
}

export async function listQueuedSightings(): Promise<QueuedSighting[]> {
  const db = await openDb()
  const result = await new Promise<QueuedSighting[]>((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, 'readonly')
    const request = tx.objectStore(STORE_NAME).getAll()
    request.onsuccess = () => resolve(request.result as QueuedSighting[])
    request.onerror = () => reject(request.error)
  })
  db.close()
  return result.sort((a, b) => a.queuedAt.localeCompare(b.queuedAt))
}

export async function removeQueuedSighting(clientReportId: string): Promise<void> {
  const db = await openDb()
  await new Promise<void>((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, 'readwrite')
    tx.objectStore(STORE_NAME).delete(clientReportId)
    tx.oncomplete = () => resolve()
    tx.onerror = () => reject(tx.error)
  })
  db.close()
}

export async function updateQueuedSighting(entry: QueuedSighting): Promise<void> {
  await enqueueSighting(entry)
}
