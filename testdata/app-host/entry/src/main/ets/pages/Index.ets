@Entry
@Component
struct Index {
  build() {
    Column({ space: 16 }) {
      Text('Go / native C network test').fontSize(24)
      Text('Running bounded checks. Results are recorded in the CI log.').fontSize(16)
    }.width('100%').height('100%').justifyContent(FlexAlign.Center).padding(32)
  }
}
