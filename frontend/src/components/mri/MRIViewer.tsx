import React, { useEffect, useRef, useState } from 'react'
import {
  AlertTriangle,
  Contrast,
  Expand,
  Layers,
  Minimize2,
  RotateCcw,
  ZoomIn,
  ZoomOut,
} from 'lucide-react'
import type { Niivue, NVImage } from '@niivue/niivue'
import { ApiClientError, apiRequest } from '@/services/apiClient'
import { Card } from '@/components/ui/Card'

type ViewerMode = 'multiplanar' | 'axial' | 'coronal' | 'sagittal' | '3d'
type PreviewStatus = 'loading' | 'ready' | 'unavailable' | 'error'
type VoxelPosition = [number, number, number]

interface MRIViewerProps {
  volumeEndpoint?: string
  previewStatus?: PreviewStatus
  unavailableReason?: string
  title?: string
}

interface VolumeMetadata {
  dimensions: number[]
  spacing: number[]
  orientation: string
  intensityRange: [number, number]
}

interface ViewerLoadState {
  endpoint: string | null
  status: PreviewStatus
  error: string | null
}

const MAX_VOLUME_SIZE_BYTES = 250 * 1024 * 1024
const VIEWER_MODES: Array<{ value: ViewerMode; label: string }> = [
  { value: 'multiplanar', label: 'MPR' },
  { value: 'axial', label: 'Axial' },
  { value: 'coronal', label: 'Coronal' },
  { value: 'sagittal', label: 'Sagittal' },
  { value: '3d', label: '3D' },
]

class MRIViewerError extends Error {}

const getAxisForMode = (mode: ViewerMode) => {
  if (mode === 'sagittal') return 0
  if (mode === 'coronal') return 1
  return 2
}

const getOrientation = (affine?: ArrayLike<number>) => {
  if (!affine || affine.length < 12) return 'Unavailable'
  const directions = ['R', 'A', 'S']
  const opposites = ['L', 'P', 'I']
  const labels = [0, 1, 2].map((axis) => {
    const column = [0, 1, 2].map((row) => Number(affine[axis * 4 + row] ?? 0))
    const dominantAxis = column.indexOf(
      Math.max(...column.map((value) => Math.abs(value))),
    )
    return column[dominantAxis]! >= 0
      ? directions[dominantAxis]
      : opposites[dominantAxis]
  })
  return labels.join('')
}

const getMetadata = (volume: NVImage): VolumeMetadata => {
  const dims = volume.dims ?? []
  const dimensions = dims.length >= 4 ? dims.slice(1, 4) : dims.slice(0, 3)
  const pixelDimensions = volume.pixDims ?? []
  const spacing =
    pixelDimensions.length >= 4
      ? pixelDimensions.slice(1, 4)
      : pixelDimensions.slice(0, 3)
  const min = volume.global_min ?? volume.cal_min ?? 0
  const max = volume.global_max ?? volume.cal_max ?? 0

  return {
    dimensions: dimensions.map(Number),
    spacing: spacing.map(Number),
    orientation: getOrientation(volume.matRAS),
    intensityRange: [Number(min), Number(max)],
  }
}

const applyWindowLevel = (viewer: Niivue, volume: NVImage, percent: number) => {
  const min = volume.global_min ?? volume.cal_min ?? 0
  const max = volume.global_max ?? volume.cal_max ?? 0
  const center = (min + max) / 2
  const halfRange = ((max - min) * percent) / 200
  volume.cal_min = center - halfRange
  volume.cal_max = center + halfRange
  viewer.updateGLVolume()
}

const resetWindowLevel = (viewer: Niivue, volume: NVImage) => {
  volume.cal_min = volume.global_min ?? volume.cal_min
  volume.cal_max = volume.global_max ?? volume.cal_max
  viewer.updateGLVolume()
}

const getViewerError = (error: unknown) => {
  if (error instanceof MRIViewerError) return error.message
  if (error instanceof ApiClientError) {
    if (error.status === 401) {
      return 'Your session has expired. Sign in again to access this MRI.'
    }
    if (error.status === 403) {
      return 'You are not authorized to view the MRI for this assessment.'
    }
    if (error.status === 404) {
      return 'The MRI volume for this assessment is no longer available.'
    }
    if (error.status === 422) {
      return 'The stored file is not a valid NIfTI volume.'
    }
    if (error.status && error.status >= 500) {
      return 'The server could not retrieve this MRI volume. Please try again.'
    }
    return error.message
  }
  return 'This file could not be decoded as a NIfTI volume. Check that it is a valid .nii or .nii.gz file.'
}

export const MRIViewer: React.FC<MRIViewerProps> = ({
  volumeEndpoint,
  previewStatus = volumeEndpoint ? 'ready' : 'unavailable',
  unavailableReason = 'No MRI volume is associated with this assessment.',
  title = 'Structural MRI Viewer',
}) => {
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const containerRef = useRef<HTMLDivElement | null>(null)
  const viewerRef = useRef<Niivue | null>(null)
  const voxelPositionRef = useRef<VoxelPosition | null>(null)
  const locationUpdateFrameRef = useRef<number | null>(null)
  const windowUpdateFrameRef = useRef<number | null>(null)
  const pendingWindowPercentRef = useRef<number | null>(null)
  const [loadState, setLoadState] = useState<ViewerLoadState>({
    endpoint: volumeEndpoint ?? null,
    status: volumeEndpoint
      ? 'loading'
      : previewStatus === 'loading'
        ? 'loading'
        : previewStatus === 'error'
          ? 'error'
          : 'unavailable',
    error: previewStatus === 'error' ? unavailableReason : null,
  })
  const [metadata, setMetadata] = useState<VolumeMetadata | null>(null)
  const [voxelPosition, setVoxelPosition] = useState<VoxelPosition | null>(null)
  const [mode, setMode] = useState<ViewerMode>('multiplanar')
  const [sliceAxis, setSliceAxis] = useState(2)
  const [windowPercent, setWindowPercent] = useState(100)
  const [zoom, setZoom] = useState(1)
  const [isExpanded, setIsExpanded] = useState(false)
  const [retryCount, setRetryCount] = useState(0)
  const stateMatchesEndpoint = loadState.endpoint === (volumeEndpoint ?? null)
  const status = stateMatchesEndpoint
    ? loadState.status
    : volumeEndpoint
      ? 'loading'
      : previewStatus === 'error'
        ? 'error'
        : previewStatus === 'loading'
          ? 'loading'
          : 'unavailable'
  const errorMessage = stateMatchesEndpoint
    ? loadState.error
    : previewStatus === 'error'
      ? unavailableReason
      : null

  useEffect(() => {
    let active = true
    let disposed = false
    let viewer: Niivue | null = null
    voxelPositionRef.current = null

    const dispose = () => {
      if (locationUpdateFrameRef.current !== null) {
        window.cancelAnimationFrame(locationUpdateFrameRef.current)
        locationUpdateFrameRef.current = null
      }
      if (windowUpdateFrameRef.current !== null) {
        window.cancelAnimationFrame(windowUpdateFrameRef.current)
        windowUpdateFrameRef.current = null
      }
      if (!viewer) return
      for (const volume of [...viewer.volumes]) {
        viewer.removeVolume(volume)
      }
      if (!disposed) {
        disposed = true
        viewer.cleanup()
      }
      if (viewerRef.current === viewer) viewerRef.current = null
    }

    if (!volumeEndpoint) {
      voxelPositionRef.current = null
      return () => {
        active = false
      }
    }

    const canvas = canvasRef.current
    if (!canvas) {
      setLoadState({
        endpoint: volumeEndpoint,
        status: 'error',
        error: 'The MRI viewer could not initialize its rendering canvas.',
      })
      return () => {
        active = false
      }
    }

    const loadVolume = async () => {
      let rendererInitialized = false
      try {
        const blob = await apiRequest<Blob>(volumeEndpoint, {
          method: 'GET',
          expectsBlob: true,
        })
        if (!(blob instanceof Blob) || blob.size === 0) {
          throw new MRIViewerError('The MRI endpoint returned an empty volume.')
        }
        if (blob.size > MAX_VOLUME_SIZE_BYTES) {
          throw new MRIViewerError(
            'This MRI volume exceeds the 250 MiB viewer limit.',
          )
        }
        if (!active) return

        const header = new Uint8Array(await blob.slice(0, 2).arrayBuffer())
        const isGzip = header[0] === 0x1f && header[1] === 0x8b
        const file = new File(
          [blob],
          `assessment-volume${isGzip ? '.nii.gz' : '.nii'}`,
          { type: 'application/octet-stream' },
        )
        const { Niivue: NiivueLibrary, DRAG_MODE } =
          await import('@niivue/niivue')
        if (!active) return
        viewer = new NiivueLibrary({
          isResizeCanvas: true,
          isColorbar: true,
          trustCalMinMax: false,
          show3Dcrosshair: true,
          mouseEventConfig: {
            leftButton: {
              primary: DRAG_MODE.crosshair,
              withShift: DRAG_MODE.pan,
              withCtrl: DRAG_MODE.contrast,
            },
            rightButton: DRAG_MODE.contrast,
            centerButton: DRAG_MODE.pan,
          },
        })
        viewerRef.current = viewer
        await viewer.attachToCanvas(canvas)
        if (!active) return
        rendererInitialized = true
        await viewer.loadFromFile(file)
        if (!active) {
          dispose()
          return
        }

        const volume = viewer.volumes[0]
        if (!volume) {
          throw new MRIViewerError(
            'The NIfTI file did not contain a readable image volume.',
          )
        }

        viewer.setColormap(volume.id, 'gray')
        viewer.setSliceType(viewer.sliceTypeMultiplanar)
        viewerRef.current = viewer
        viewer.onLocationChange = (location: unknown) => {
          if (
            typeof location !== 'object' ||
            location === null ||
            !('vox' in location)
          ) {
            return
          }
          const voxels = location.vox
          if (
            typeof voxels !== 'object' ||
            voxels === null ||
            !('length' in voxels) ||
            typeof voxels.length !== 'number'
          ) return
          const coordinates = voxels as ArrayLike<unknown>
          const nextPosition = [
            Number(coordinates[0]),
            Number(coordinates[1]),
            Number(coordinates[2]),
          ] as VoxelPosition
          if (!nextPosition.every(Number.isFinite)) return

          voxelPositionRef.current = nextPosition
          if (locationUpdateFrameRef.current !== null) {
            window.cancelAnimationFrame(locationUpdateFrameRef.current)
          }
          locationUpdateFrameRef.current = window.requestAnimationFrame(() => {
            locationUpdateFrameRef.current = null
            if (active) setVoxelPosition(nextPosition)
          })
        }

        const volumeMetadata = getMetadata(volume)
        setMetadata(volumeMetadata)
        const centerPosition: VoxelPosition = [
          Math.floor(((volumeMetadata.dimensions[0] ?? 1) - 1) / 2),
          Math.floor(((volumeMetadata.dimensions[1] ?? 1) - 1) / 2),
          Math.floor(((volumeMetadata.dimensions[2] ?? 1) - 1) / 2),
        ]
        voxelPositionRef.current = centerPosition
        setVoxelPosition(centerPosition)
        setWindowPercent(100)
        setZoom(1)
        setLoadState({ endpoint: volumeEndpoint, status: 'ready', error: null })
      } catch (loadError) {
        if (active) {
          setLoadState({
            endpoint: volumeEndpoint,
            status: 'error',
            error:
              loadError instanceof ApiClientError ||
              loadError instanceof MRIViewerError ||
              rendererInitialized
                ? getViewerError(loadError)
                : 'Unable to initialize the browser MRI renderer. Verify that WebGL is enabled and try again.',
          })
        }
        dispose()
      }
    }

    void loadVolume()

    return () => {
      active = false
      dispose()
    }
  }, [volumeEndpoint, retryCount])

  useEffect(() => {
    if (!isExpanded) return
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setIsExpanded(false)
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [isExpanded])

  const setViewerMode = (nextMode: ViewerMode) => {
    const viewer = viewerRef.current
    if (!viewer) return
    setMode(nextMode)
    if (nextMode === 'multiplanar') {
      viewer.setSliceType(viewer.sliceTypeMultiplanar)
    } else if (nextMode === '3d') {
      viewer.setSliceType(viewer.sliceTypeRender)
    } else if (nextMode === 'axial') {
      viewer.setSliceType(viewer.sliceTypeAxial)
    } else if (nextMode === 'coronal') {
      viewer.setSliceType(viewer.sliceTypeCoronal)
    } else {
      viewer.setSliceType(viewer.sliceTypeSagittal)
    }
    if (nextMode !== '3d') {
      const axis = getAxisForMode(nextMode)
      setSliceAxis(axis)
    }
  }

  const handleSliceChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const viewer = viewerRef.current
    const currentPosition = voxelPositionRef.current ?? voxelPosition
    const maxVoxel = Math.max((metadata?.dimensions[sliceAxis] ?? 1) - 1, 0)
    const nextVoxel = Math.min(maxVoxel, Math.max(0, Number(event.target.value)))
    if (!viewer || !currentPosition || !Number.isFinite(nextVoxel)) return
    const delta = nextVoxel - currentPosition[sliceAxis]
    if (delta === 0) return
    const movement = [0, 0, 0]
    movement[sliceAxis] = delta
    const nextPosition = [...currentPosition] as VoxelPosition
    nextPosition[sliceAxis] = nextVoxel
    voxelPositionRef.current = nextPosition
    setVoxelPosition(nextPosition)
    viewer.moveCrosshairInVox(movement[0]!, movement[1]!, movement[2]!)
  }

  const handleWindowChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const nextPercent = Number(event.target.value)
    setWindowPercent(nextPercent)
    pendingWindowPercentRef.current = nextPercent
    if (windowUpdateFrameRef.current !== null) return
    windowUpdateFrameRef.current = window.requestAnimationFrame(() => {
      windowUpdateFrameRef.current = null
      const percent = pendingWindowPercentRef.current
      const viewer = viewerRef.current
      const volume = viewer?.volumes[0]
      if (percent === null || !viewer || !volume) return
      applyWindowLevel(viewer, volume, percent)
    })
  }

  const handleZoom = (factor: number) => {
    const viewer = viewerRef.current
    if (!viewer) return
    const nextZoom = Math.min(4, Math.max(0.5, zoom * factor))
    const [panX, panY, panZ] = viewer.scene.pan2Dxyzmm
    const pan = new Float32Array([panX, panY, panZ, nextZoom])
    viewer.setPan2Dxyzmm(pan)
    setZoom(nextZoom)
  }

  const resetView = () => {
    const viewer = viewerRef.current
    if (!viewer) return
    const pan = new Float32Array([0, 0, 0, 1])
    viewer.setPan2Dxyzmm(pan)

    if (metadata) {
      const center = metadata.dimensions.map((dimension) =>
        Math.floor((dimension - 1) / 2),
      )
      const current = voxelPosition ?? center
      viewer.moveCrosshairInVox(
        center[0]! - current[0]!,
        center[1]! - current[1]!,
        center[2]! - current[2]!,
      )
    }
    const volume = viewer.volumes[0]
    if (volume) {
      resetWindowLevel(viewer, volume)
    }
    setWindowPercent(100)
    setZoom(1)
    setViewerMode('multiplanar')
  }

  const toggleExpanded = () => {
    setIsExpanded((expanded) => !expanded)
  }

  const currentSlice = voxelPosition?.[sliceAxis] ?? 0
  const sliceCount = metadata?.dimensions[sliceAxis] ?? 1
  const intensityMin = metadata?.intensityRange[0]
  const intensityMax = metadata?.intensityRange[1]

  return (
    <Card
      className={`flex flex-col gap-4 ${
        isExpanded
          ? 'fixed inset-0 z-[100] overflow-auto rounded-none bg-[#0a0b0e] p-4 sm:p-6'
          : ''
      }`}
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2">
          <Layers className="h-4 w-4 shrink-0 text-[#5eead4]" />
          <span className="truncate font-mono text-sm font-semibold uppercase tracking-wide text-[#ebecef]">
            {title}
          </span>
        </div>
        <button
          type="button"
          onClick={toggleExpanded}
          aria-label={
            isExpanded ? 'Exit fullscreen MRI viewer' : 'Expand MRI viewer'
          }
          className="rounded-lg border border-white/10 bg-white/5 p-2 text-[#c6c9d2] transition-colors hover:bg-white/10"
        >
          {isExpanded ? (
            <Minimize2 className="h-4 w-4" />
          ) : (
            <Expand className="h-4 w-4" />
          )}
        </button>
      </div>

      {status === 'ready' ? (
        <div
          className="flex flex-wrap gap-2"
          aria-label="MRI viewing modes"
          role="group"
        >
          {VIEWER_MODES.map((item) => (
            <button
              key={item.value}
              type="button"
              onClick={() => setViewerMode(item.value)}
              aria-pressed={mode === item.value}
              className={`rounded-md px-2.5 py-1.5 text-xs font-mono uppercase transition-colors ${
                mode === item.value
                  ? 'border border-[#5eead4]/30 bg-[#5eead4]/15 text-[#5eead4]'
                  : 'bg-white/5 text-[#8d909c] hover:text-[#ebecef]'
              }`}
            >
              {item.label}
            </button>
          ))}
        </div>
      ) : null}

      <div
        ref={containerRef}
        className={`relative overflow-hidden rounded-lg border border-white/10 bg-[#07080b] ${
          isExpanded
            ? 'h-[calc(100vh-12rem)] min-h-[65vh] flex-1'
            : 'h-[min(70vh,680px)] min-h-[360px] sm:min-h-[440px]'
        }`}
      >
        <canvas
          ref={canvasRef}
          aria-label="Interactive multiplanar NIfTI MRI volume"
          aria-hidden={status !== 'ready'}
          className={`h-full w-full outline-none ${
            status === 'ready' ? '' : 'opacity-0'
          }`}
          tabIndex={status === 'ready' ? 0 : -1}
        />
        {status === 'loading' ? (
          <div
            className="absolute inset-0 flex flex-col items-center justify-center gap-3 text-[#c6c9d2]"
            role="status"
            aria-live="polite"
          >
            <div className="h-10 w-10 animate-spin rounded-full border-2 border-[#5eead4] border-t-transparent" />
            <span className="font-mono text-xs uppercase tracking-[0.16em] text-[#8d909c]">
              Loading MRI volume
            </span>
            <span className="max-w-md px-6 text-center text-xs text-[#6d7280]">
              Large scans can take a moment to transfer and render.
            </span>
          </div>
        ) : status === 'error' ? (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-4 px-6 text-center">
            <AlertTriangle className="h-8 w-8 text-[#fb923c]" />
            <p
              role="alert"
              className="max-w-lg text-sm leading-7 text-[#c6c9d2]"
            >
              {errorMessage ?? 'The MRI volume could not be displayed.'}
            </p>
            {volumeEndpoint ? (
              <button
                type="button"
                onClick={() => {
                  setLoadState({
                    endpoint: volumeEndpoint ?? null,
                    status: 'loading',
                    error: null,
                  })
                  setRetryCount((count) => count + 1)
                }}
                className="rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-[#ebecef] hover:bg-white/10"
              >
                Try again
              </button>
            ) : null}
          </div>
        ) : status === 'unavailable' ? (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-4 px-6 text-center">
            <AlertTriangle className="h-8 w-8 text-[#8d909c]" />
            <p className="max-w-lg text-sm leading-7 text-[#c6c9d2]">
              {unavailableReason}
            </p>
          </div>
        ) : null}
      </div>

      {status === 'ready' ? (
        <>
          <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_auto]">
            <div className="space-y-4">
              {mode !== '3d' ? (
                <label className="block space-y-2 text-xs text-[#8d909c]">
                  <span className="flex justify-between font-mono uppercase">
                    <span>Slice position</span>
                    <span className="text-[#ebecef]">
                      {Math.round(currentSlice) + 1} / {sliceCount}
                    </span>
                  </span>
                  <input
                    type="range"
                    min="0"
                    max={Math.max(sliceCount - 1, 0)}
                    step="1"
                    value={Math.min(currentSlice, Math.max(sliceCount - 1, 0))}
                    onChange={handleSliceChange}
                    aria-label="Select MRI slice position"
                    className="h-3 w-full cursor-pointer appearance-none rounded-lg bg-[#1f222d] accent-[#5eead4]"
                  />
                </label>
              ) : null}
              <label className="block space-y-2 text-xs text-[#8d909c]">
                <span className="flex justify-between font-mono uppercase">
                  <span className="flex items-center gap-1">
                    <Contrast className="h-3.5 w-3.5" /> Window / level
                  </span>
                  <span className="text-[#ebecef]">{windowPercent}%</span>
                </span>
                <input
                  type="range"
                  min="10"
                  max="100"
                  step="1"
                  value={windowPercent}
                  onChange={handleWindowChange}
                  aria-label="Adjust MRI window level"
                  className="h-3 w-full cursor-pointer appearance-none rounded-lg bg-[#1f222d] accent-[#5eead4]"
                />
              </label>
            </div>

            <div className="flex items-start gap-2">
              <button
                type="button"
                onClick={() => handleZoom(1 / 1.1)}
                aria-label="Zoom out"
                className="rounded-lg border border-white/10 bg-white/5 p-2 text-[#c6c9d2] hover:bg-white/10"
              >
                <ZoomOut className="h-4 w-4" />
              </button>
              <button
                type="button"
                onClick={() => handleZoom(1.1)}
                aria-label="Zoom in"
                className="rounded-lg border border-white/10 bg-white/5 p-2 text-[#c6c9d2] hover:bg-white/10"
              >
                <ZoomIn className="h-4 w-4" />
              </button>
              <button
                type="button"
                onClick={resetView}
                aria-label="Reset MRI view"
                className="inline-flex items-center gap-2 rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-xs text-[#c6c9d2] hover:bg-white/10"
              >
                <RotateCcw className="h-4 w-4" />
                Reset
              </button>
            </div>
          </div>

          {metadata ? (
            <dl className="grid grid-cols-2 gap-3 rounded-lg border border-white/10 bg-white/[0.03] p-3 text-xs sm:grid-cols-4">
              <div>
                <dt className="text-[#8d909c]">Dimensions</dt>
                <dd className="mt-1 font-mono text-[#c6c9d2]">
                  {metadata.dimensions.join(' × ') || 'Unavailable'} voxels
                </dd>
              </div>
              <div>
                <dt className="text-[#8d909c]">Voxel spacing</dt>
                <dd className="mt-1 font-mono text-[#c6c9d2]">
                  {metadata.spacing.length
                    ? `${metadata.spacing.map((value) => value.toFixed(2)).join(' × ')} mm`
                    : 'Unavailable'}
                </dd>
              </div>
              <div>
                <dt className="text-[#8d909c]">Orientation</dt>
                <dd className="mt-1 font-mono text-[#c6c9d2]">
                  {metadata.orientation}
                </dd>
              </div>
              <div>
                <dt className="text-[#8d909c]">Voxel intensity range</dt>
                <dd className="mt-1 font-mono text-[#c6c9d2]">
                  {Number.isFinite(intensityMin) &&
                  Number.isFinite(intensityMax)
                    ? `${intensityMin} to ${intensityMax}`
                    : 'Unavailable'}
                </dd>
              </div>
            </dl>
          ) : null}

          <p className="text-xs leading-5 text-[#8d909c]">
            Scroll over a view to move through slices. Click to reposition the
            synchronized crosshairs; Shift-drag or middle-drag to pan. Use the
            window / level control to adjust grayscale intensity.
          </p>
        </>
      ) : null}
    </Card>
  )
}
