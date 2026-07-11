<script setup lang="ts">
import { ref } from 'vue'
import { addFriend } from '@/api/social'
import { ElMessage } from 'element-plus'

const emit = defineEmits<{ added: [] }>()

const visible = defineModel<boolean>('visible', { default: false })
const friendTsNickname = ref('')
const loading = ref(false)

async function handleAdd() {
  if (!friendTsNickname.value.trim()) {
    ElMessage.warning('请输入好友 TS 昵称')
    return
  }

  loading.value = true
  try {
    const res = await addFriend(friendTsNickname.value.trim())
    if (res.success) {
      let message = '好友添加成功'

      // 如果好友在线，显示额外提示
      if (res.friend_online) {
        const gameText = res.game ? `（正在 ${res.game}）` : ''
        message += `，对方当前在线${gameText}！`
      }

      ElMessage.success(message)
      friendTsNickname.value = ''
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
      <el-form-item label="好友 TS 昵称">
        <el-input v-model="friendTsNickname" placeholder="输入好友的 TS 昵称" size="large" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :loading="loading" @click="handleAdd">添加</el-button>
    </template>
  </el-dialog>
</template>
