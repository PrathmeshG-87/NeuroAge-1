# MRI dataset preparation for brain-age modeling

## 1. Goal

This repository includes a reproducible dataset-preparation pipeline for structural MRI brain-age studies. The pipeline is designed to:

- inventory candidate MRI scans
- align them to a subject-level metadata file
- detect corrupted or low-quality files
- identify duplicates and repeated scans
- produce a transparent data-quality summary
- keep the raw dataset immutable and store derived outputs in a separate directory

The repository does not contain a real patient dataset. Any real dataset must be obtained through approved access and must comply with institutional and legal requirements before use.

## 2. Recommended dataset choices

The project should use a dataset that has:

- structural T1-weighted MRI scans
- reliable chronological-age labels
- enough sample size for train/validation/test partitioning
- subject identifiers for leakage-safe splitting
- approved terms of use and release conditions

### Candidate datasets

| Dataset | Typical use | Strengths | Caveats |
| --- | --- | --- | --- |
| IXI | Development and method validation | Publicly used in MRI research, cross-sectional adult brain scans | Access and licensing must be confirmed; not all users may be allowed to re-use it without institutional approval |
| OASIS | Brain-age and aging studies | Broad age coverage and well-documented metadata | Access restrictions vary by release and consent terms |
| ADNI | Clinical aging research | Large age range and clinical metadata | ADNI has strict access conditions and requires formal approval |

The default recommendation is to start with a dataset that is approved for the project and has clear age metadata, such as IXI or OASIS, if the team has the required access. ADNI may be considered only when the project has the necessary institutional review and data-use approvals.

## 3. Data dictionary

A typical manifest file should include at least the following columns:

- `subject_id`: stable per-subject identifier used for leakage-safe splitting
- `age`: chronological age in years as a float or integer
- `sex`: optional biological sex or demographic grouping, if permitted
- `scan_id`: optional scan identifier when multiple time points exist
- `modality`: expected value such as `T1`, `T1w`, or `MPRAGE`
- `site`: scanner site or acquisition center, if available
- `acquisition_date`: date of scan, if permitted
- `visit`: visit number, if longitudinal data are included

The exact schema depends on the source dataset and approved data-use terms.

## 4. Inclusion and exclusion policy

Recommended inclusion policy:

- include one MRI scan per subject in the final modeling set, unless the research protocol explicitly allows repeated scans
- keep the earliest or highest-quality scan per subject for the base dataset
- mark all other scans from the same subject as duplicates and exclude them from the analysis set
- exclude files with missing or invalid age labels
- exclude corrupted or unreadable files
- reject non-3D/4D NIfTI arrays with impossible dimensions

Recommended exclusion reasons:

- missing age label
- invalid age (< 0 or > 120)
- duplicate subject scan
- corrupted or unreadable NIfTI file
- non-structural or unsupported dimensions
- incomplete metadata or malformed subject identifier

## 5. Data safety and immutability

The project must keep the raw dataset immutable. Derived outputs should be saved into a separate directory, for example:

- raw dataset: `data/raw/`
- derived metadata and reports: `data/derived/`
- quality summaries: `data/derived/dataset_quality_summary.json`

The pipeline never modifies source files. It creates new derived files only.

## 6. Local configuration

Use environment variables instead of hardcoded directories.

Example `.env` entries:

```env
DATASET_ROOT=./data/raw
DATASET_METADATA_PATH=./data/raw/metadata.csv
DATASET_DERIVED_DIR=./data/derived
```

From the `backend/` directory, run the inventory script as follows:

```bash
python scripts/dataset_inventory.py \
  --dataset-root "$DATASET_ROOT" \
  --metadata-path "$DATASET_METADATA_PATH" \
  --output-dir "$DATASET_DERIVED_DIR"
```

If the data are not locally available, the script will raise a clear error that explains the required directory and how to obtain an approved dataset.

## 7. Data-use and privacy safeguards

The project must not:

- upload MRI data to external services without explicit authorization and a privacy review
- create synthetic MRI data and label it as real data
- claim research performance from synthetic or demo files
- use data without confirming the approved uses and restrictions

## 8. Deliverables

This repository includes:

- the reproducible data inventory script: `backend/scripts/dataset_inventory.py`
- the analysis module: `backend/app/data_pipeline/dataset_inventory.py`
- the dataset documentation: this file
- a generated quality report in the derived directory produced by the script

The quality report includes counts, age statistics, missingness, duplicate scans, and exclusion reasons in a machine-readable JSON format.
