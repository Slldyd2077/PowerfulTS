<script setup lang="ts">
import { ref } from 'vue'
import { addFriend } from '@/api/social'
import { ElMessage } from 'element-plus'

const emit = defineEmits<{ added: [] }>()

const visible = defineModel<boolean>('visible', { default: false })
const friendQq = ref('')
const loading = ref(false)

async function handleAdd() {
  if (!friendQq.value.trim()) {
    ElMessage.warning('请输入好友 QQ 号')
    return
  }

  loading.value = true
  try {
    const res = await addFriend(friendQq.value.trim())
    if (res.success) {
      ElMessage.success('好友添加成功')
      friendQq.value = ''
      visible.value = false
      emit('added')
    } else {
      ElMessage.error(res.error || '添加失败')
    }
  } catch (e: unknown) {
    ElMessage.error(e instanceof Error ? e.message : '添加失败')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <el-dialog v-model="visible" title="添加好友" width="400px" :close-on-click-modal="false">
    <el-form @submit.prevent="handleAdd" label-position="top">
      <el-form-item label="好友 QQ 号">
        <el-input v-model="friendQq" placeholder="输入好友的 QQ 号" size="large" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :loading="loading" @click="handleAdd">添加</el-button>
    </template>
  </el-dialog>
</template>
