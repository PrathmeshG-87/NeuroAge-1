import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { apiRequest, ApiClientError } from '@/services/apiClient'
import { MRIViewer } from './MRIViewer'

const niivueState = vi.hoisted(() => ({
  instances: [] as Array<Record<string, unknown>>,
}))

vi.mock('@/services/apiClient', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/services/apiClient')>()
  return {
    ...actual,
    apiRequest: vi.fn(),
  }
})

vi.mock('@niivue/niivue', () => {
  class MockNiivue {
    volumes = [
      {
        id: 'volume-1',
        dims: [3, 6, 7, 8, 1, 1, 1, 1],
        pixDims: [1, 1, 1.1, 1.2, 1, 1, 1, 1],
        matRAS: new Float32Array([
          1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1,
        ]),
        global_min: 0,
        global_max: 100,
        cal_min: 0,
        cal_max: 100,
      },
    ]
    scene = { pan2Dxyzmm: new Float32Array([0, 0, 0, 1]) }
    sliceTypeMultiplanar = 'multiplanar'
    sliceTypeAxial = 'axial'
    sliceTypeCoronal = 'coronal'
    sliceTypeSagittal = 'sagittal'
    sliceTypeRender = '3d'
    onLocationChange: (location: unknown) => void = () => {}
    position = [2, 3, 3]
    attachToCanvas = vi.fn(async () => this)
    loadFromFile = vi.fn(async (_file: File) => {})
    setColormap = vi.fn()
    setSliceType = vi.fn()
    setPan2Dxyzmm = vi.fn((pan: Float32Array) => {
      this.scene.pan2Dxyzmm = new Float32Array(pan)
    })
    moveCrosshairInVox = vi.fn((x: number, y: number, z: number) => {
      this.position = [
        this.position[0]! + x,
        this.position[1]! + y,
        this.position[2]! + z,
      ]
      this.onLocationChange({ vox: new Float32Array(this.position) })
    })
    updateGLVolume = vi.fn()
    removeVolume = vi.fn((volume: unknown) => {
      this.volumes = this.volumes.filter((entry) => entry !== volume)
    })
    cleanup = vi.fn()

    constructor() {
      niivueState.instances.push(this as unknown as Record<string, unknown>)
    }
  }

  return {
    Niivue: MockNiivue,
    DRAG_MODE: {
      crosshair: 8,
      pan: 3,
      contrast: 1,
    },
  }
})

interface MockViewer {
  volumes: Array<{
    cal_min?: number
    cal_max?: number
  }>
  attachToCanvas: ReturnType<typeof vi.fn>
  loadFromFile: ReturnType<typeof vi.fn>
  setColormap: ReturnType<typeof vi.fn>
  setSliceType: ReturnType<typeof vi.fn>
  setPan2Dxyzmm: ReturnType<typeof vi.fn>
  moveCrosshairInVox: ReturnType<typeof vi.fn>
  updateGLVolume: ReturnType<typeof vi.fn>
  removeVolume: ReturnType<typeof vi.fn>
  cleanup: ReturnType<typeof vi.fn>
}

describe('MRIViewer', () => {
  afterEach(() => {
    vi.clearAllMocks()
    niivueState.instances.length = 0
  })

  it.each([
    [
      'uncompressed NIfTI',
      new Uint8Array([0, 1, 2, 3]),
      'assessment-volume.nii',
    ],
    [
      'gzip-compressed NIfTI',
      new Uint8Array([0x1f, 0x8b, 0, 0]),
      'assessment-volume.nii.gz',
    ],
  ])(
    'loads actual %s bytes in the browser viewer',
    async (_label, bytes, fileName) => {
      vi.mocked(apiRequest).mockResolvedValue(
        new Blob([bytes], { type: 'application/octet-stream' }),
      )

      render(
        <MRIViewer
          previewStatus="ready"
          volumeEndpoint="/api/v1/assessments/test/mri/volume"
        />,
      )

      expect(await screen.findByText('6 × 7 × 8 voxels')).toBeInTheDocument()
      expect(apiRequest).toHaveBeenCalledWith(
        '/api/v1/assessments/test/mri/volume',
        expect.objectContaining({ method: 'GET', expectsBlob: true }),
      )
      expect(niivueState.instances).toHaveLength(1)

      const viewer = niivueState.instances[0] as unknown as MockViewer
      expect(viewer.loadFromFile).toHaveBeenCalledWith(
        expect.objectContaining({ name: fileName }),
      )
      expect(viewer.setColormap).toHaveBeenCalledWith('volume-1', 'gray')
      expect(viewer.setSliceType).toHaveBeenCalledWith('multiplanar')
      expect(screen.getByText('RAS')).toBeInTheDocument()
    },
  )

  it('changes view, slice position, intensity window, and resets the view', async () => {
    vi.mocked(apiRequest).mockResolvedValue(
      new Blob([new Uint8Array([0, 1, 2, 3])]),
    )

    render(
      <MRIViewer
        volumeEndpoint="/api/v1/assessments/test/mri/volume"
        previewStatus="ready"
      />,
    )
    await screen.findByText('6 × 7 × 8 voxels')

    const viewer = niivueState.instances[0] as unknown as MockViewer
    fireEvent.click(screen.getByRole('button', { name: 'Coronal' }))
    expect(viewer.setSliceType).toHaveBeenLastCalledWith('coronal')

    fireEvent.change(
      screen.getByRole('slider', { name: 'Select MRI slice position' }),
      {
        target: { value: '5' },
      },
    )
    expect(viewer.moveCrosshairInVox).toHaveBeenLastCalledWith(0, 2, 0)
    expect(
      screen.getByRole('slider', { name: 'Select MRI slice position' }),
    ).toHaveValue('5')
    expect(screen.getByText('6 / 7')).toBeInTheDocument()

    fireEvent.change(
      screen.getByRole('slider', { name: 'Adjust MRI window level' }),
      {
        target: { value: '50' },
      },
    )
    await waitFor(() => {
      expect(viewer.volumes[0]?.cal_min).toBe(25)
      expect(viewer.volumes[0]?.cal_max).toBe(75)
      expect(viewer.updateGLVolume).toHaveBeenCalled()
    })

    fireEvent.click(screen.getByRole('button', { name: 'Zoom in' }))
    expect(viewer.setPan2Dxyzmm).toHaveBeenLastCalledWith(
      new Float32Array([0, 0, 0, 1.1]),
    )
    fireEvent.click(screen.getByRole('button', { name: 'Reset MRI view' }))
    expect(viewer.setSliceType).toHaveBeenLastCalledWith('multiplanar')
    expect(viewer.volumes[0]?.cal_min).toBe(0)
    expect(viewer.volumes[0]?.cal_max).toBe(100)
  })

  it('cleans the old renderer and reloads the volume when assessments change', async () => {
    vi.mocked(apiRequest).mockResolvedValue(
      new Blob([new Uint8Array([0, 1, 2, 3])]),
    )
    const { rerender } = render(
      <MRIViewer
        volumeEndpoint="/api/v1/assessments/first/mri/volume"
        previewStatus="ready"
      />,
    )
    await screen.findByText('6 × 7 × 8 voxels')

    const firstViewer = niivueState.instances[0] as unknown as MockViewer
    rerender(
      <MRIViewer
        volumeEndpoint="/api/v1/assessments/second/mri/volume"
        previewStatus="ready"
      />,
    )

    await waitFor(() => {
      expect(apiRequest).toHaveBeenLastCalledWith(
        '/api/v1/assessments/second/mri/volume',
        expect.objectContaining({ expectsBlob: true }),
      )
      expect(niivueState.instances).toHaveLength(2)
    })
    expect(firstViewer.removeVolume).toHaveBeenCalled()
    expect(firstViewer.cleanup).toHaveBeenCalled()
  })

  it('shows an authorization message instead of exposing a request error', async () => {
    vi.mocked(apiRequest).mockRejectedValue(
      new ApiClientError('private server detail', { status: 403 }),
    )

    render(
      <MRIViewer
        volumeEndpoint="/api/v1/assessments/forbidden/mri/volume"
        previewStatus="ready"
      />,
    )

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'You are not authorized to view the MRI for this assessment.',
    )
    expect(screen.queryByText('private server detail')).not.toBeInTheDocument()
  })
})
