# Dataset and preprocessing record

## Scope

This repository is designed for reproducible brain-age research using structural MRI, but it does not include a permitted research dataset or trained model weights in the repo itself. Any real training or evaluation must use an approved source and a dataset access pathway that satisfies institutional review, licensing, and redistribution rules.

## Approved data sources and access

The project is compatible with the following research workflows, subject to access approval:

- IXI: used for local method development and validation when institutionally approved
- OASIS: used when the project has explicit permission to use the release
- ADNI: only when the project has the required data-use approval, approvals, and secure storage environment

Required provenance fields for a real dataset manifest:

- dataset_name
- access_date
- source_url or access_channel
- version or release identifier
- permissible_use statement
- licensing or approval reference
- checksum or manifest hash if redistributed locally

Do not commit restricted MRI files, data manifests containing identifiers, or source files that the repository is not permitted to redistribute.

## Data-quality and exclusion rules

The repository uses the following rules before any model training or evaluation begins:

- exclude files that are unreadable or corrupted
- exclude missing or impossible age labels
- exclude values outside the valid range of 0 to 120 years
- require a unique subject_id for subject-level splitting
- exclude duplicate scans for the same subject unless the research design explicitly allows longitudinal analysis
- reject unsupported image dimensionality or empty arrays
- record all exclusions in a machine-readable report

All exclusion logic should be documented in the derived dataset summary, not just in ad hoc notes.

## Preprocessing configuration

The canonical preprocessing configuration used by the project is defined by the `PreprocessingConfig` model in [preprocessing.py](../backend/app/data_pipeline/preprocessing.py):

- target_shape: `(128, 128, 128)` by default
- orientation: `RAS`
- resample_voxel_spacing: `None` unless a scanner-aware resampling policy is explicitly configured
- clip_percentiles: `(1.0, 99.0)`
- normalize: `zscore`
- dtype: `float32`
- ensure_3d: `True`
- seed: `42`

The preprocessing pipeline is deterministic for the same input file and config and must preserve the same device-agnostic numeric conversion rules.

## Subject-level train/validation/test manifests

The project supports subject-level splitting to prevent leakage between partitions. The split uses `subject_id` as the partition key instead of scan ID or voxel-level data.

Recommended usage:

```python
from app.data_pipeline.preprocessing import SubjectSplitConfig, build_subject_split_manifest

config = SubjectSplitConfig(test_fraction=0.2, val_fraction=0.1, seed=42)
manifest = build_subject_split_manifest('data/raw/metadata.csv', split_config=config)
print(manifest['train'])
print(manifest['val'])
print(manifest['test'])
```

This ensures there is no overlap between training, validation, and test subject sets.

## Random seeds and reproducibility

For reproducible experiments, record:

- random seed for subject splits
- random seed for model initialization, if applicable
- package versions and Python version
- data manifest version and checksum
- preprocessing config version

The repository currently uses a fixed seed of `42` for preprocessing and split logic unless a different configuration is intentionally selected.

## Training and evaluation environment

Use a documented environment with at least:

- Python 3.13 or the project-supported interpreter
- NumPy, NiBabel, and pytest versions pinned for the working environment
- scikit-learn or the selected model dependency set, if training uses it
- a stable local or secure remote storage location for the approved data

Do not commit secrets, temporary MRI files, model checkpoints, or restricted files into the Git repository.

## Reproduction commands

To inspect and summarize a permitted dataset:

```bash
python -c "from app.data_pipeline.dataset_inventory import analyze_dataset; print(analyze_dataset('data/raw', metadata_path='data/raw/metadata.csv', output_dir='data/derived'))"
```

To save and inspect preprocessing configuration:

```bash
python -c "from app.data_pipeline.preprocessing import PreprocessingConfig, save_preprocessing_config; cfg = PreprocessingConfig(); save_preprocessing_config(cfg, 'data/derived/preprocessing_config.json'); print(cfg.to_dict())"
```

To preprocess a single MRI file against the repo config:

```bash
python -c "from app.data_pipeline.preprocessing import preprocess_image, PreprocessingConfig; data = preprocess_image('path/to/scan.nii.gz', PreprocessingConfig()); print(data.shape)"
```

## Research limitations

The repository’s current code and tests validate reproducibility, data quality, and inference behavior with synthetic or authorized test fixtures. They do not establish scientific validity for a real clinical or research brain-age model. Any real cohort evaluation must be accompanied by a documented dataset access record, model artifact metadata, and careful interpretation of uncertainty and bias.
